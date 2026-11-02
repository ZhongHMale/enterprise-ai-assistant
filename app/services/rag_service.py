"""
RAG 服务：检索 + 路由 + 记忆 + 基于资料回答
===========================================
职责：
  1. search()：粗筛（pgvector 向量检索）+ 精排（Rerank）→ 最相关片段
  2. answer()：检索结果 + 问题 → 模型基于资料回答
  3. routed_answer()：路由版问答（先判断要不要查资料，闲聊直接答）
     + 多轮记忆（按 session_id 持久化到 PostgreSQL）

记忆说明（企业版）：
  - 普通问答（/chat）的记忆存在 chat_messages 表（PostgreSQL），重启不丢
  - 智能体模式（/chat/agent）的记忆走 LangGraph 检查点（PostgreSQL）
  - 两种模式都是数据库持久化，多实例共享
"""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy import select

from app.config import USE_RERANK
from app.core.llm import get_llm
from app.db import SessionLocal
from app.models import ChatMessage
from app.services import document_service
from app.services.intent_service import classify_question
from app.services.rerank_service import rerank

# 每个会话最多记住几轮（防止历史无限膨胀，控制 token 成本）
_MAX_HISTORY_ROUNDS = 10


def _history_text(session_id: str, max_rounds: int = 5) -> str:
    """从数据库读最近几轮历史，拼成文本塞进提示词"""
    with SessionLocal() as db:
        rows = (
            db.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.id.desc())
                .limit(max_rounds * 2)  # 每轮 2 条（用户+AI）
            )
            .scalars()
            .all()
        )
    rows.reverse()  # 倒序取回来的是"最新在前"，翻正成"最早在前"
    if not rows:
        return "（无）"
    lines = [f"{'用户' if m.role == 'user' else 'AI'}：{m.content}" for m in rows]
    return "\n".join(lines)


def _save_turn(session_id: str, user_msg: str, ai_msg: str) -> None:
    """把一轮对话写进数据库（chat_messages 表）"""
    with SessionLocal() as db:
        db.add(ChatMessage(session_id=session_id, role="user", content=user_msg))
        db.add(ChatMessage(session_id=session_id, role="ai", content=ai_msg))
        db.commit()


def _clean_history(session_id: str) -> None:
    """历史超过上限时，删掉最旧的（保留最近 _MAX_HISTORY_ROUNDS 轮）"""
    with SessionLocal() as db:
        rows = (
            db.execute(
                select(ChatMessage.id)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.id.desc())
                .offset(_MAX_HISTORY_ROUNDS * 2)
            )
            .scalars()
            .all()
        )
        if rows:
            db.execute(
                ChatMessage.__table__.delete().where(ChatMessage.id.in_(rows))
            )
            db.commit()


# RAG 回答提示词：企业级三段式（见深度专题2）+ 历史
_RAG_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """你是一名资深HR，负责解答员工关于公司制度的咨询。

历史对话：
{history}

请根据下面提供的参考资料回答问题。

参考资料：
{context}

规则：
1. 只根据参考资料回答，禁止编造
2. 资料中没有相关信息时，回答"资料中未找到相关信息"
3. 用中文口语化回答，不超过150字""",
        ),
        ("human", "员工问题：{question}"),
    ]
)

# 闲聊回答提示词（不查资料，直接聊，记得住历史）
_CHAT_PROMPT = ChatPromptTemplate.from_template(
    """历史对话：
{history}

请友好地回应（不超过两句话）：{question}"""
)


def search(question: str, k: int = 3) -> list[str]:
    """混合检索（向量 + BM25 → RRF 融合）→ 粗筛 → 精排（Rerank）→ 返回最相关的 k 段"""
    # ① 混合检索粗筛：多捞一些（k*3），给 Rerank 留挑选空间（两段式检索）
    coarse = document_service.search_hybrid(question, k=min(k * 3, 10))

    # ② 精排：Rerank 可用就用，不可用降级为原顺序（不阻断主流程）
    if USE_RERANK and coarse:
        try:
            results = rerank(question, coarse, top_n=min(k, len(coarse)))
            ranked = [coarse[r["index"]] for r in results if r["index"] < len(coarse)]
            if ranked:
                return ranked
        except Exception as e:
            print(f"  ⚠️ Rerank 不可用，降级为原顺序: {type(e).__name__}: {e}")
    return coarse[:k]


def answer(question: str, session_id: str, k: int = 3) -> str:
    """RAG 问答：检索（含精排） + 组装 + 模型回答"""
    context = "\n\n---\n\n".join(search(question, k=k))
    history = _history_text(session_id)

    chain = _RAG_PROMPT | get_llm(temperature=0.2) | StrOutputParser()
    return chain.invoke({"context": context, "question": question, "history": history})


def routed_answer(question: str, session_id: str = "default", k: int = 3) -> str:
    """路由版问答（带记忆）：
    1. 先用结构化分类判断"要不要查知识库"
    2. 制度类 → RAG；闲聊/其他 → 直接回答（省一次检索）
    3. 分类失败时降级走 RAG（宁可多查，不能答错）
    4. 回答后把（问题, 回答）记进该会话的历史"""
    history = _history_text(session_id)

    try:
        intent = classify_question(question)
        print(f"  [意图] 类别={intent.category}  需要知识库={intent.needs_knowledge_base}  摘要={intent.summary}")
        if not intent.needs_knowledge_base:
            chain = _CHAT_PROMPT | get_llm(temperature=0.7) | StrOutputParser()
            reply = chain.invoke({"question": question, "history": history})
        else:
            reply = answer(question, session_id, k=k)
    except Exception as e:
        # 降级：意图识别挂了也不能让问答崩掉 → 走 RAG
        print(f"  ⚠️ 意图识别失败，降级走 RAG: {type(e).__name__}: {e}")
        reply = answer(question, session_id, k=k)

    # 记忆：把这轮对话写进数据库（PostgreSQL）
    _save_turn(session_id, question, reply)
    _clean_history(session_id)  # 超上限清最旧的，控制成本

    return reply
