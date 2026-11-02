# 🤖 企业智能助手（Enterprise AI Assistant）

> **这是一个完整的多文件企业级项目**，不是单文件示例。
> 它把课程里学的一切（LangChain + LangGraph + RAG + 工具调用 + 人机审批 + FastAPI + 测试 + Docker）组织成生产风格的工程。

---

## 界面截图

**用户端**（`/`）：RAG 制度问答 · 智能体工具调用 + 人工审批

<p align="center">
  <img src="../docs/screenshots/02-chat-rag.png" width="49%" alt="RAG 制度问答">
  <img src="../docs/screenshots/03-chat-agent-approval.png" width="49%" alt="Agent 审批中断">
</p>

**管理后台**（`/admin`）：用户管理 · 审批记录（合规审计）

<p align="center">
  <img src="../docs/screenshots/04-admin-users.png" width="49%" alt="用户管理">
  <img src="../docs/screenshots/06-admin-approvals.png" width="49%" alt="审批记录">
</p>

---

## 一、项目简介

一个企业内部 AI 助手：员工可以问公司制度（RAG）、让它算数/查天气（工具）、发通知（需人工审批）；管理者可以在后台管理知识库文档。

**核心能力**

| 能力 | 技术 | 对应文件 |
|------|------|---------|
| 制度问答（RAG） | **混合检索（向量+BM25→RRF）** + **Rerank 精排** | `document_service.py` + `rag_service.py` |
| **问题路由** | **结构化输出（with_structured_output）**：先分类再决定查不查库 | `app/services/intent_service.py` |
| 工具调用（Agent） | LangGraph ReAct 循环 + **实时天气 API（Open-Meteo，含降级）** | `app/graph/workflow.py` + `tools/weather.py` |
| 多轮记忆 | PostgreSQL（chat_messages 表 / 检查点） | `rag_service.py` + `core/memory.py` |
| 人工审批（HITL） | interrupt + 恢复 + **审批审计入库（所有路径）** | `app/graph/workflow.py` |
| 流式接口 | FastAPI + SSE（前端打字机） | `app/routers/chat.py` |
| 用户体系 | **注册/登录（JWT）+ 角色权限 + 头像（emoji/照片上传）** | `app/routers/auth.py` |
| 知识库管理 | 上传/删除/列表（增删改查） | `app/routers/admin.py` |
| **前端（Vue 3）** | **用户端 + 管理后台两个页面（前后端分离）** | `app/static/index.html` + `admin.html` |
| **可观测性** | **LangSmith 全链路追踪** | `app/main.py` + `.env` |
| **评测** | **测试集 + 关键词命中打分** | `evaluate.py` |
| 自动化测试 | pytest（含混合检索 RRF 测试） | `tests/` |

## 二、项目一图流（全文件速查，复习/面试用）

### 数据流总览：一条请求怎么穿过整个系统

```
用户（Swagger / 前端）
   │ HTTP
   ▼
┌────────────────────────────────────────────────────────┐
│ ① 接口层  app/routers/        （柜台：接单转手）         │
│    chat.py      /chat、/chat/stream、/chat/agent、审批   │
│    admin.py     /admin/documents（知识库管理）           │
│    只看 import 和 return——它只传话，不干活               │
└──────────────┬─────────────────────────────────────────┘
               │ 调用
┌──────────────▼─────────────────────────────────────────┐
│ ② 业务层  app/services/       （后厨：真正干活）         │
│    rag_service.py     路由版问答（意图→检索→回答）       │
│    intent_service.py  结构化输出：把问题分类             │
│    rerank_service.py  粗筛后精排（失败自动降级）         │
│    document_service.py 文档加载→切分→入库→检索           │
│    agent_service.py   调度员：run(接单) + approve(审批)  │
│    三层保障：模型自主→强制重试→确定性兜底               │
└──────────────┬─────────────────────────────────────────┘
               │ 调用
┌──────────────▼─────────────────────────────────────────┐
│ ③ 流程图  app/graph/          （流水线：ReAct 循环）     │
│    state.py     白板定义（State：messages 等）           │
│    workflow.py  ★核心：agent节点→条件边→tools节点→循环   │
│                 interrupt() 审批中断在这里               │
└──────────────┬─────────────────────────────────────────┘
               │ 调用
┌──────────────▼─────────────────────────────────────────┐
│ ④ 基础设施  app/core/  +  app/tools/  （手脚）          │
│    core/llm.py      模型工厂（换模型只改这里）           │
│    core/memory.py   检查点（thread_id 记忆）             │
│    tools/           4个工具：手册检索/计算/天气/发通知    │
│    schemas/         菜单：接口收发格式（Pydantic）       │
└────────────────────────────────────────────────────────┘
```

### 每个文件一句话职责（速查表）

| 文件 | 一句话 | 层级 |
|------|--------|------|
| `main.py` | 入口：注册路由 + 启动建知识库 | 总机 |
| `config.py` | 所有配置（密钥/模型/Rerank/LangSmith） | 配置 |
| `routers/chat.py` | 4 个聊天窗口（接单转手） | 接口层 |
| `routers/admin.py` | 知识库管理窗口（上传/列表） | 接口层 |
| `schemas/chat.py` | 接口收发格式（Pydantic 菜单） | 契约 |
| `services/rag_service.py` | 路由版 RAG 问答 | 业务层 |
| `services/intent_service.py` | 意图分类（结构化输出） | 业务层 |
| `services/rerank_service.py` | 检索精排（含降级） | 业务层 |
| `services/document_service.py` | 文档入库 + 检索 | 业务层 |
| `services/agent_service.py` | Agent 调度：接单 + 审批 | 业务层 |
| `graph/state.py` | 白板定义 | 流程 |
| `graph/workflow.py` | ★ ReAct 循环 + 审批中断 | 流程 |
| `core/llm.py` | 模型工厂 | 基础设施 |
| `core/memory.py` | 检查点记忆 | 基础设施 |
| `tools/calculator.py` | 计算工具 | 工具 |
| `tools/weather.py` | 天气工具 | 工具 |
| `tools/handbook.py` | 手册检索工具 | 工具 |
| `tools/notice.py` | 发通知工具（需审批） | 工具 |
| `evaluate.py` | 评测脚本（测试集打分） | 工具 |
| `tests/` | pytest 自动化测试 | 测试 |
| `Dockerfile` | 容器化部署 | 部署 |

### 三个"只读关键行"技巧（看代码不迷路）

1. **看文件先看顶部 docstring**（每个文件都写了"干嘛的"）
2. **接口层看 return，业务层看函数名，流程层看 add_edge**
3. **带 `_` 开头的函数先跳过**（内部小工具，用到再看）

> 📖 **想把每个函数"为什么存在"彻底搞懂**，看
> [`08-工程通识/06-五层结构实战讲解.md`](../08-工程通识/06-五层结构实战讲解.md)：
> 它按 接口层/服务层/工具层/数据层/测试层 逐层拆解本项目，
> 给出"需求 → 该改哪些文件"对照表、5 个动手练法，以及一个真实 bug 的发现与修复全过程。

```
                    ┌─────────────────────────────────────────┐
  前端/用户 ──HTTP──▶│  FastAPI (app/main.py)                  │
                    │  ├─ /chat        普通问答                │
                    │  ├─ /chat/stream SSE 流式               │
                    │  ├─ /agent       智能体（带审批）        │
                    │  ├─ /agent/approve 人工审批             │
                    │  └─ /admin/documents 知识库管理          │
                    └──────────────┬──────────────────────────┘
                                   │ 调用
                    ┌──────────────▼──────────────────────────┐
                    │  服务层 (app/services/)                  │
                    │  agent_service ── 编排 LangGraph 图      │
                    │  rag_service   ── 检索 + 组装回答        │
                    │  document_service ── 文档加载/切分/入库  │
                    └──────┬───────────────────────┬──────────┘
                           │                       │
              ┌────────────▼───────┐   ┌───────────▼──────────┐
              │ LangGraph 流程图    │   │ 向量库 + 工具         │
              │ (app/graph/)       │   │ (app/tools/)         │
              │ 思考→工具→审批→回答 │   │ 手册检索/计算/天气    │
              └────────────┬───────┘   └───────────┬──────────┘
                           │                       │
              ┌────────────▼───────┐   ┌───────────▼──────────┐
              │ 模型工厂(app/core)  │   │ 数据(app/data/*.txt) │
              │ DeepSeek 等 API    │   │ 员工手册等知识文档    │
              └────────────────────┘   └──────────────────────┘
```

## 三、快速开始

```bash
# 0. 用独立虚拟环境（推荐；已在课程根目录激活过 .venv 的可以跳过 0~1）
python -m venv .venv                # Windows：创建虚拟环境
.venv\Scripts\activate              # 激活（命令行出现 (.venv)）

# 1. 安装依赖（Python 3.10+）
pip install -r requirements.txt

# 2. 配置密钥：把课程根目录的 .env 复制到本项目根目录（或参照 .env.example 新建）

# 3. 启动服务
uvicorn app.main:app --reload --port 8000

# 4. 打开交互文档
#    浏览器访问 http://127.0.0.1:8000/docs
```

**常用接口（Swagger 里都能点）**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat` | 普通问答 |
| POST | `/chat/stream` | RAG 流式问答（SSE 打字机） |
| POST | `/agent` | 智能体问答（需要审批时会停下等你批） |
| POST | `/agent/approve` | 人工审批（同意/拒绝） |
| POST | `/admin/documents` | 上传文档进知识库 |
| GET | `/admin/documents` | 查看知识库文档列表 |
| GET | `/health` | 健康检查 |

**一键体验智能体 + 审批流程：**

```bash
# 1) 提问触发"发通知"工具（会停在审批处）
curl -X POST http://127.0.0.1:8000/agent \
  -H "Content-Type: application/json" \
  -d '{"message": "给张三发一条通知：明天上午10点开周会", "session_id": "test1"}'
# 返回 status=awaiting_approval，拿到审批详情

# 2) 人工批准
curl -X POST http://127.0.0.1:8000/agent/approve \
  -H "Content-Type: application/json" \
  -d '{"thread_id": "test1", "approve": true}'
```

## 四、项目结构说明（面试怎么讲）

| 目录 | 职责 | 面试点 |
|------|------|--------|
| `routers/` | HTTP 接口层 | 只做参数校验和返回，不含业务逻辑 |
| `services/` | 业务逻辑层 | RAG/Agent 编排都在这，可独立测试 |
| `tools/` | 工具层 | 每个工具一个文件，新增工具=加一个文件 |
| `graph/` | LangGraph 流程图 | 状态、节点、边、审批中断 |
| `core/` | 基础设施 | 模型工厂（换模型只改这里）、记忆存储 |
| `schemas/` | 数据模型 | Pydantic，接口契约 |
| `tests/` | 测试 | 假模型模拟，不联网不烧钱 |

**分层的好处（面试必答）**：接口层不写业务、业务层不碰 HTTP；每层可单独测试；换模型/换向量库只动 core/。

## 五、运行测试

```bash
pip install pytest httpx
python -m pytest tests/ -v
```

预期结果：**29 passed, 3 skipped**（跳过的是需要数据库的 3 个集成测试；`docker compose up -d` 后去掉 `test_document_service.py` 里的 skip 即可跑）。

测试分层设计：大部分测试**不需要数据库、不需要 API 密钥**，几秒跑完——
因为核心逻辑（RRF 融合 `rrf_fuse`、切分分组 `_split_by_document`、通知路由判断 `_looks_like_notice_request`）都被抽成了纯函数。

## 六、评测（用数据证明系统效果）

```bash
python evaluate.py
```

原理：测试集（问题+期望关键词）→ 跑一遍系统 → 统计命中率。
**改切分/加 Rerank/换模型后重跑，分数涨了=改对了**。这是面试"怎么证明系统好"的标准答案。

## 七、可观测性（LangSmith，可选）

在 `.env` 配好 `LANGCHAIN_TRACING_V2`、`LANGCHAIN_API_KEY` 后，
每次调用自动上报云端，可回放完整链路（提示词、检索结果、延迟、费用）——生产排障必备。

## 八、Docker 部署（应用容器化）

```bash
docker build -t ai-assistant .
docker run -p 8000:8000 --env-file .env ai-assistant
```

## 九、企业版（PostgreSQL + 鉴权 + 审计）

本项目已从"教学演示版"升级为"企业生产版"：

| 教学版 | 企业版 | 解决什么问题 |
|--------|--------|-------------|
| 内存检查点（重启丢记忆） | **PostgreSQL 检查点**（`PostgresSaver`） | 重启不丢、多实例共享 |
| 内存向量库 | **pgvector 向量检索**（document_chunks 表） | 数据落盘、可扩容 |
| 文件系统存文档 | **documents 表**（SQLAlchemy ORM） | 可查询、可统计 |
| 无鉴权 | **JWT 登录 + 角色**（admin/employee） | 安全底线 |
| print 日志 | **loguru 结构化日志**（logs/app.log） | 生产排障 |
| 无审批记录 | **approval_records 表**（审计） | 合规要求 |

### 企业版启动步骤

```bash
# 1. 启动数据库
#    默认数据存在项目内 ./pgdata（克隆下来直接跑，不用改配置）
#    想让"代码与数据分离"，就在 .env 里加一行：PGDATA_DIR=D:/my-data/pgdata
docker compose up -d

# 2. 安装新增依赖
pip install -r requirements.txt

# 3. 启动服务
uvicorn app.main:app --reload --port 8000
```

### 登录（新接口）

| 接口 | 说明 |
|------|------|
| `POST /auth/login` | 登录：`admin` / `admin123` → 拿令牌 |
| `GET /auth/me` | 查看当前用户 |

Swagger 用法：先调 `/auth/login` 拿 `access_token` → 点右上角 **Authorize** 粘贴 → 之后 `/admin/*`、`/chat/agent/approve` 自动带上令牌。

> 💡 数据库没启动时服务也能启动（`/health` 正常），业务接口会报数据库错误——这是"启动失败不致命"的设计。

## 十、项目亮点总结（简历/面试用）

1. **生产风格分层架构**：接口/业务/工具/图/基础设施分离，符合企业代码规范
2. **完整 RAG 链路**：文档上传→切分→向量化（pgvector）→粗筛→**Rerank 精排**→回答
3. **问题路由**：结构化输出先分类，闲聊不查库，省成本省延迟
4. **LangGraph Agent**：ReAct 循环 + 工具调用 + 检查点记忆（PostgreSQL）+ 人工审批闭环
5. **企业级工程**：JWT 鉴权、审批审计、loguru 日志、SQLAlchemy + pgvector、pytest、LangSmith、FastAPI+SSE、Docker
