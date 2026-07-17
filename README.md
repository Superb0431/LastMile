<div align="center">

# LastMile

**一个针对医院难以触及的“医疗最后一公里”设计的医疗信息记录Agent**

医生问自己病史，总是模糊不清？好不容易开了药总是忘了吃？结果看不懂，总是忧心忡忡？LastMile may work!

<p>
  <img src="https://img.shields.io/badge/python-≥3.11-blue" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-async-009688" alt="FastAPI">
  <img src="https://img.shields.io/badge/Redis-Streams-DC382D" alt="Redis">
  <img src="https://img.shields.io/badge/LiteLLM-DeepSeek-412991" alt="LiteLLM">
  <img src="https://img.shields.io/badge/Docker-ready-2496ED" alt="Docker">
</p>

</div>

🏥 **LastMile** 是一个可自托管的医疗信息记录Agent：具备流式对话、HITL审批、病历与症状时间线生成、药品安全检查、指南检索，以及会时刻想着整理记忆的功能。  

## First Run

| 章节 | 去这里 |
|---|---|
| LastMile可以做什么？ | [LastMile可以做什么？](#what-lastmile-can-do) |
| LastMile技术实现 | [LastMile技术实现](#lastmile-implementation) |
| 快速开始 | [🚀 Quick Start](#quick-start) |
| 参数配置 | [⚙️ Configuration](#configuration) |
| 内置工具 | [🧰 Built-in Tools](#built-in-tools) |
| 项目结构 | [📁 Layout](#layout) |
| 额外注意 | [🛡️ 额外注意](#额外注意) |
| 声明 | [声明](#disclaimer) |

<a id="what-lastmile-can-do"></a>

## LastMile可以做什么？

LastMile 面向出院后/慢病管理/日常健康随访这类真实对话场景。它可以：

- 像**微信聊天**一样和你对话；
- 查病史、读病史、写病史，整理每一条健康记录；
- 定期主动询问和记录你的病情，判断你是否严格遵守医嘱，以及你的情况是否需要去医院复查；
- 本地部署了药物相互作用与禁忌症表、特殊类药品识别等工具，自动帮你判断你拿到的新药适不适合吃。
- 回复时会参考本地医学文档与指南，并在回复末尾标注来源。


<a id="lastmile-implementation"></a>

## LastMile技术实现
- 采用Agent-as-Tool架构，基于ReAct范式完成任务规划与执行，结合Harness Engineering提升系统稳定性。
- 上下文与记忆系统：对会话记忆、工具描述、用户病史、动态提示词等内容分层存储、按需注入和更新，稳定的上下文前缀设计保证最大程度利用缓存。缓存心跳机制定期向provider发送小体量包刷新Cache。
- 工具机制：对多种工具约束输入和输出，具备重试与降级机制和基于Redis的工具结果缓存系统。
- Agent安全设计：具备高危操作审核能力；Safe模式可以筛选可信来源数据；针对注入攻击等手段进行多重防护。
- Agent Eval：该项目Agent能力主要基于记忆的分析和整理能力，因此采用MedMemoryBench进行评测以迭代版本。
- 工程化：基于FastAPI和Redis Streams构建异步任务队列，由5个Worker的消费者组抢占任务，应对并发需求；使用Docker Compose将服务容器化，实现故障隔离。
- 病史系统：由三大核心机制，Profile、EHR（就诊记录）、Interval（院外症状）组成，跨对话保留信息。
- **LightDream Agent** 在后台整理信息，**DeepDream Agent**整理记忆，缓解Lost-In-The-Middle问题。
- 每个会话可以随时追溯，避免跨会话遗忘问题。


<a id="quick-start"></a>

## 🚀 Quick Start
### 方法一：Github Clone
### 你需要准备

- Python **3.11+**
- **Redis服务**（本地启动或Docker启动）
- 至少两个LLM API Key
- **Tavily** API Key（联网搜索工具）

### 1. Clone项目到本地并安装依赖

```bash
cd LastMile
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```
API与其他参数请在`.env`中配置，用编辑器打开 `.env`，至少填这三项：

```env
API_KEY=
LIGHT_DREAM_API_KEY=
TAVILY_API_KEY=
```


本地部署Redis请确认端口号是否为6379：

```env
REDIS_URL=redis://localhost:6379/0
```


### 3. 启动Redis

本机已安装Redis时,请执行命令：

```bash
redis-server
```

或者只用Docker启动Redis：

```bash
docker run -d --name lastmile-redis -p 6379:6379 redis:7-alpine
```

> [!TIP]
> Redis启动失败时，API仍会启动，但**Redis工具缓存会失效，且任务队列不可用**——整个服务将无法继续，所以正式使用请保证Redis在线。

### 4. 启动 API 与 Worker（两个进程）

在项目根目录：

```bash
# 终端 1：API
uvicorn backend.main:app --reload --port 8000

# 终端 2：Worker
python -m backend.worker
```

### 5. 打开界面

浏览器访问：[http://127.0.0.1:8000/](http://127.0.0.1:8000/)

输入用户名进入聊天。需要联网搜索时，界面会弹出同意 / 拒绝——这就是 HITL。

如果走到这里还能正常回一句「你好」，恭喜，LastMile 已经在你机器上活起来了。

### 方法二：Docker部署

若选择Docker部署，请按顺序运行如下命令：

```bash
copy .env.example .env
# 别忘了配置 API_KEY、TAVILY_API_KEY等
docker compose up --build
```

Compose 会拉起：

| 服务 | 职责 |
|---|---|
| `redis` | 缓存 + Streams 队列 |
| `api` | FastAPI + 静态前端 |
| `worker` | 真正跑 AgentLoop 的消费者 |

打开 [http://127.0.0.1:8000/](http://127.0.0.1:8000/) 即可运行程序。

<a id="configuration"></a>

## ⚙️ Configuration

所有运行时配置经项目根目录 `.env` 注入，由 **`backend/config.py`** 统一读取（唯一配置中心）。

### 最少必填

| 变量 | 说明 |
|---|---|
| `API_KEY` | 主模型 API Key |
| `TAVILY_API_KEY` | 联网搜索 API Key |

### 配置地图

| 分组 | 代表变量 | 用途 |
|---|---|---|
| 主 Agent | `API_KEY`、`MAIN_MODEL`、`API_BASE` | 对话模型与可选网关 |
| Light Dream | `LIGHT_DREAM_API_KEY`、`LIGHT_DREAM_MODEL` | 记忆整理；未填回退主配置 |
| 文档子 Agent | `DOCS_AGENT_MODEL`、`DOCS_AGENT_API_KEY`、`DOCS_AGENT_API_BASE` | `read_docs`；未填回退主配置 |
| 搜索 | `TAVILY_API_KEY`、`SEARCH_SAFE_MODE` | 搜索与白名单模式 |
| 上下文 | `MODEL_CONTEXT_WINDOW` | token 窗口 / 压缩判断 |
| Redis / 队列 | `REDIS_URL`、`TOOL_CACHE_*`、`APPROVAL_*`、`WORKER_*`、`TASK_*` | 缓存、审批超时、并发与认领 |
| LiteLLM 统计 | `ENABLE_LLM_STATS`、`LITELLM_*` | 可选 Proxy / Token 统计 |
| 安全审查 | `SECURITY_*`、`PROMPT_GUARD_*`、`HF_TOKEN` | 输入 / 流式 / 最终三级 |
| 评测 | `EVAL_MODE` | 接入MedMemoryBench评测数据进行评测 |


> [!IMPORTANT]
> 开启任一 `SECURITY_*_SEMANTIC=true` 前，请先安装 `requirements.txt` 末尾注释掉的 `transformers` / `torch`，并按需填写 `HF_TOKEN`。默认关闭语义检测，开箱更轻。

详细的默认值与注释请直接阅读 [`.env.example`](./.env.example)。

<a id="built-in-tools"></a>

## 🧰 Built-in Tools

Agent 通过注册表暴露工具，工具采用渐进式加载策略，Agent主要可以使用包括但不限于如下的工具：

| 工具 | 做什么 | 备注 |
|---|---|---|
| `web_search` | Tavily 联网搜索 | **需 HITL 审批** |
| `read_record` / `write_record` | 读/写 Profile、EHR、Interval | 按用户隔离 |
| `check_drug_danger` | 高危 / 特殊管理药品查询 | 适用于药物推荐等场景 |
| `drug_interaction`（相互作用） | 药物相互作用与禁忌检查 | 基于本地知识库 |
| `read_docs` | 检索本地医学文档 / 指南 | 可带子 Agent |
| `tools_loader` / `skill_loader` | 查看工具说明、加载 Skill | 控制工具权限 |

知识数据在 `backend/data/`（药品库、文档索引、指南原文）。需要重建时，可用同目录下的 `build_*.py`。

<a id="layout"></a>

## 📁 Layout

```
LastMile/
├── backend/
│   ├── main.py              # FastAPI 入口（submit / result / approve）
│   ├── worker.py            # Redis Streams 消费者
│   ├── config.py            # 配置中心
│   ├── agent/               # AgentLoop、LLM、安全、Dream…
│   ├── tools/               # 工具注册表与实现
│   ├── memory/              # 每用户 SQLite
│   ├── prompts/             # 系统提示词（产品逻辑，不是文档）
│   ├── queue/               # Redis 总线
│   ├── sub_agents/          # 文档子 Agent 等
│   ├── skills/              # Skill 包
│   ├── data/                # 知识库与索引
│   └── users/               # 运行时用户数据（不入库）
├── frontend/index.html      # 聊天 WebUI
├── .env.example             # 环境变量百科
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

<a id="额外注意"></a>

## 🛡️ 额外注意

- 安全审查默认开启关键词路径；语义路径按需打开，推荐使用PromptGuard模型
- `EVAL_MODE` 只给自动化评测用，会关掉安全审查并改变部分行为——生产环境保持关闭


<a id="disclaimer"></a>

## 声明

本项目用于研究与产品原型。输出内容仅供健康管理参考，AI生成的内容**不构成医疗建议**，无法代替医生的诊断能力。部署到真实用户前，请自行完成合规、隐私与安全评估。

---

<p align="center">
  <em>Thanks for stopping by — 愿 LastMile 帮你把随访这件事，走完最后一公里。</em>
</p>
