# 项目 AI Agent 化建议

> 生成时间：2026-06-28 · 基于对 `backend/` + `frontend/` 全量探索

---

## 一、现状诊断：你已经有的「半成品 agent 骨架」

项目**不是从零开始 agent 化**，你已经有相当扎实的基础设施，只是缺了关键的「自主决策层」。

### ✅ 已有的 agent 基础设施

| 组件 | 位置 | 现状 |
|------|------|------|
| 工具调用循环 | `backend/app/core/ai_client.py::chat_with_tools()` | 固定 3 轮 observe→act 循环，最后一轮强制 `tool_choice=none` |
| 多模型格式兼容 | `ai_client.py::_try_parse_inline_tool_calls()` | 兼容 Kimi `<\|tool_call_begin\|>` / DSML `<｜DSML｜>` 内联格式 |
| 写作领域工具 | `backend/app/services/chapter_tools.py` | 15 个查询工具：query_character / query_memory / query_outline / generate_item 等，OpenAI function-calling 格式 |
| MCP 工具桥接 | `backend/app/services/mcp_client_service.py` | 从外部 MCP Server 发现工具并执行，自动转 OpenAI 格式（`mcp_` 前缀） |
| 提示词模板引擎 | `backend/app/skills/engine.py` | 40+ Skill，支持 stream / JSON / tool-calling 三种模式，自动注入上下文块 |
| 异步任务 + 进度推送 | `background_task.py` + `TaskProgressTracker` + WebSocket | 任务化执行 + 实时进度 |
| 两阶段编排雏形 | `api/routes/projects_pkg/outlines.py` | 续写时「先收集（带工具）→再生成（不带工具）」的 agent 式流程 |

### ❌ 真正的差距：为什么还不是真正的 agent

1. **循环是硬截断的，非自主终止** — `max_rounds=3`，模型不能根据任务复杂度自己决定何时完成。
2. **无显式 reasoning / planning** — 只有 `budget_hint` 文字提示，没有独立的「思考→制定计划」步骤。
3. **工具结果被盲目 append** — 查到没查到都直接塞回 messages，没有「信息是否充分」的语义判断。
4. **无会话状态持久化** — 没有 `Session` / `Message` / `Conversation` 表，每次都是无状态一次性调用，无法多轮对话、无法回溯。
5. **流程由代码预定义，AI 不能自主拆解** — 「先收集再生成」是写死在 `outlines.py` 里的两阶段，AI 不能自己决定要不要查记忆、要不要调 MCP、要不要自审。
6. **前端是黑盒** — 表单提交→轮询，用户看不到 AI 正在调哪个工具、得到什么结果，无法中途介入/纠偏。

---

## 二、Agent 化的四个改造方向（按风险从低到高）

### 🟢 方向 1：开放工具循环 + 显式思考步骤（改造现有 `chat_with_tools`）

**目标**：把固定 3 轮循环升级为「模型自主终止 + 显式 think 步骤」的 ReAct 风格循环。

**改动点**：
- `backend/app/core/ai_client.py` — 新增 `agent_loop()` 方法（替代/并存于 `chat_with_tools`）：
  - 移除 `max_rounds` 硬上限，改为 `max_iterations`（如 20）+ 空转检测（连续 2 轮无新信息则终止）。
  - 引入 `finish` 虚拟工具：模型调用 `finish(reason)` 即表示任务完成，否则继续。
  - 每轮记录 `thought`（可选，让模型先输出推理再决定调哪个工具）。
- `chapter_tools.py` / outlines.py 的两阶段收集逻辑可简化为单次 `agent_loop()` 调用。

**风险**：低。纯后端、纯函数级改造，不碰数据模型，现有调用方可以渐进迁移。

**受影响文件**：
- `backend/app/core/ai_client.py`（核心）
- `backend/app/services/chapter_tools.py`（加 `finish` 工具）
- `backend/app/api/routes/projects_pkg/outlines.py`（两阶段→单循环）

---

### 🟡 方向 2：会话与消息持久化（新增 `Session` / `Message` 数据模型）

**目标**：让 agent 具备「记忆」，支持多轮对话、回溯、人在回路（human-in-the-loop）。

**新增模型**：
```python
# backend/app/models/agent_session.py
class AgentSession(Base):
    id, project_id, user_id, task_type, status, created_at, ...
    # status: planning | running | paused | completed | failed

class AgentMessage(Base):
    id, session_id, role(system|user|assistant|tool|thought),
    content, tool_name, tool_args, tool_result, tokens, created_at
```

**配套 API**：
- `POST /projects/{pid}/agent/sessions` — 创建会话
- `GET /projects/{pid}/agent/sessions/{sid}` — 拉取会话历史（含工具调用轨迹）
- `POST /projects/{pid}/agent/sessions/{sid}/messages` — 追加用户消息（触发 agent 继续）
- `POST /projects/{pid}/agent/sessions/{sid}/pause` / `/resume` — 暂停/恢复

**风险**：中。涉及数据库迁移、新路由、前端会话 UI。

**受影响文件**：
- 新增 `backend/app/models/agent_session.py`、`agent_message.py`
- 新增 `backend/app/api/routes/projects_pkg/agent.py`
- `backend/app/main.py`（注册路由）
- 前端新增 `frontend/pages/agent-chat.vue` + `frontend/composables/useAgent.ts`

---

### 🟠 方向 3：Skill → Agent Tool 注册（让 Skill 成为 agent 可调用的原子能力）

**目标**：当前 `skills/` 是「提示词模板」，agent 化后应让这些 Skill 成为 agent 可自主调用的「思考工具」。例如 agent 在写章节时可以自主调用 `chapter_planner` skill 先规划、再调 `chapter_generation` skill 写作。

**改动点**：
- `backend/app/skills/engine.py` — 增加 `as_agent_tool()` 装饰，把 Skill 包装成 OpenAI function-calling 格式（`Skill` 表已有 `as_tool` 字段，现在真正用起来）。
- `chapter_tools.py` — 把已注册为 `as_tool=True` 的 Skill 注入工具列表，agent 循环中可调用。
- 这样 agent 的工具箱从「15 个查询工具」扩展到「15 查询 + 40 思考工具」，能自主规划「先规划再写」。

**风险**：中。需要处理好 Skill 的输入输出 schema 与工具调用的映射。

**受影响文件**：
- `backend/app/skills/engine.py`
- `backend/app/services/chapter_tools.py`
- `backend/app/skills/builtin.py`（为每个 Skill 补 tool schema）

---

### 🔴 方向 4：前端 agent 可视化 + 人在回路

**目标**：让用户能看到 agent 的 plan → act → observe 全过程，并能在任意步骤暂停、追问、纠偏。

**前端改造**：
- 新增 `frontend/components/AgentTimeline.vue` — 时间轴展示每一步（thought / tool_call / tool_result），类似 OpenAI Operator / Devin 的执行轨迹 UI。
- `BatchGeneratePanel.vue` 改造 — 从「一键提交黑盒」变为「实时展示 agent 决策过程」，每章生成时显示：正在分析大纲 → 查询记忆 → 生成正文 → 自审。
- 流式通道：当前只有 REST + 轮询，需要补 **SSE 或 WebSocket** 把 agent 每一步实时推给前端（`useChapterStream.ts` 名不副实，真正实现它）。
- 人在回路：agent 在关键节点（如「准备生成第 50 章，但前 49 章有未解决的伏笔」）可暂停请求用户确认。

**风险**：高。前端工作量大，需要稳定的实时通信通道。

**受影响文件**：
- `frontend/composables/useChapterStream.ts`（真正实现流式）
- 新增 `frontend/components/AgentTimeline.vue`
- `frontend/components/BatchGeneratePanel.vue`（重构）
- `frontend/composables/useAgent.ts`（新增）
- 后端补 SSE/WebSocket 推送端点

---

## 三、推荐落地顺序（MVP 优先）

### 第 1 步（1-2 天，立竿见影）：方向 1 的「开放循环」

只改 `ai_client.py` 的 `chat_with_tools` → `agent_loop`，加 `finish` 虚拟工具，移除硬截断。**这是所有后续工作的地基**——没有自主循环，其他都是空谈。

**验证**：用现有的章节续写场景测试，对比「3 轮硬截断」与「自主终止」的生成质量。

---

### 第 2 步（3-5 天）：方向 3 的「Skill as Tool」

让 agent 在循环中能自主调用 `chapter_planner` / `plot_analysis` 等 Skill。改动集中在 `engine.py` 和 `chapter_tools.py`，不需要新数据模型。

**验证**：观察 agent 是否会自主决定「先规划再写」，而不是每次都直接生成。

---

### 第 3 步（1 周）：方向 2 的「会话持久化」

新增 `AgentSession` / `AgentMessage` 表 + 基础 CRUD API。这一步让 agent 有了记忆，前端可以查询历史。

**验证**：能在一次会话中多轮追问（「这段再加点伏笔」「把反派改得更阴险」），agent 能基于历史上下文继续。

---

### 第 4 步（1-2 周）：方向 4 的「前端可视化 + 人在回路」

最后做前端，因为它依赖前三步的产出。重点是把 agent 的执行过程从黑盒变成透明，这是「agent 感」的核心体验。

---

## 四、关键设计决策

### Q1：要不要引入 LangGraph / AutoGen / OpenAI Agents SDK？

**建议：暂不引入**。你的 `chat_with_tools` 已经实现了 ReAct 循环的核心，且深度适配了 Kimi/DSML 等国产模型的非标准格式——这些是现成框架难以覆盖的。自己实现 `agent_loop` 控制力更强，迁移成本更低。

如果后续需要复杂的多 agent 协作（如「主笔 agent + 审稿 agent + 设定 agent」并行），再评估 LangGraph。

### Q2：会话状态存数据库还是 Redis？

**建议：核心状态（Session/Message）存数据库**，方便回溯和审计；**实时进度和工具调用流**走 Redis pub/sub + WebSocket，降低数据库写入压力。

### Q3：流式用 SSE 还是 WebSocket？

**建议：SSE**。你的场景是「服务端→客户端」的单向流（agent 的 think/act/observe 过程），SSE 比 WebSocket 简单得多，且 Nuxt/FastAPI 都有成熟支持。WebSocket 留给未来真正的双向交互（如 agent 主动问用户）。

### Q4：已有的「两阶段收集→生成」要不要保留？

**建议：保留但可选**。方向 1 的 `agent_loop` 实现后，两阶段编排可以作为 `agent_loop` 的一个 preset（预定义工具集 + 系统提示），而不是写死在 `outlines.py` 里的代码流程。这样既兼容现有行为，又给 agent 自主决策留了空间。

---

## 五、一句话总结

> 你的项目不是「要不要 agent 化」的问题，而是「把已经写好的 agent 骨架补上大脑」——**开放循环 + 显式思考 + 会话记忆 + 前端可视化**，四步走，每一步都能独立交付价值。

第一步（开放 `agent_loop`）是性价比最高的起点，建议今天就动。