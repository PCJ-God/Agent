# Agent 智能教学助手 — 项目理解 & 修改 Review（已归档）

> **本文档已归档**：记录的是早前一次会话的中间状态，其中的问题清单多已处理，**请勿作为当前代码的说明使用**。
>
> 归档时点，第 5 节「发现但未修改的问题」的处理情况：
>
> | 原编号 | 问题 | 现状 |
> |---|---|---|
> | 5.1 | MCP 工具与 Skill 从未接入任何 Agent | **已修复** — 现由 `ToolPool` 统一抓取一次，再分发给三个 Agent |
> | 5.2 | 存储层未接线、多个配置项无人读取 | **已处理** — 长期记忆已接入；`MEMORY_STRATEGY` / `TEMPERATURE` / `BASE_URL` / `DATA_DIR` 已删除 |
> | 5.3 | CLI 与 Server 的 MCP 注册逻辑重复 | **已修复** — 两者统一走 `HierarchicalTeam.create()` |
> | 5.5 | ContextTruncation 分支会复现 tiktoken 卡死 | **已删除** — 随死文件 `short_term.py` 一并移除 |
>
> 第 3 节的改动清单同样已过期（其后又完成了记忆 / 工具 / 规划三项增强，并做过一轮冗余清理）。
> 当前代码说明请以 `README.md` 为准。

> 本文档记录三件事：① 对项目架构的理解；② 本会话对代码的**全部**修改（按主题分组，含前后对比、原因、验证证据）；③ 发现但**尚未修改**的问题。
>
> 覆盖范围：共 6 组改动、8 个文件。行号均为当前磁盘上的真实位置。

---

## 一、项目概览

基于 **AgentScope** 的多 Agent 层级协作系统（智能教学助手），采用四层架构。

| 项 | 说明 |
|----|------|
| 框架 | AgentScope 1.0.18（`ReActAgent` / `Toolkit` / `Msg` / `DashScopeChatModel` / `DashScopeChatFormatter`） |
| 模型服务 | 阿里云 DashScope（兼容 OpenAI 模式），默认 `qwen-plus`，当前 `.env` 配置为 `qwen3-vl-flash` |
| Python | 3.10+（代码中使用了运行时 `X \| None` 联合类型注解） |
| 入口 | CLI（`scripts/run_agent.py`）+ FastAPI（`scripts/run_server.py`）+ 原生 HTML 前端 |
| 配置 | `src/config.py`（读 `.env`）+ `configs/agent_config.yaml`（**注：该 YAML 无任何代码读取**） |
| 记忆 | 短期记忆 `InMemoryMemory` + agentscope 内置历史自动压缩（见 3.6） |

### 四层架构与职责

| 层级 | 位置 | 职责 | 现状 |
|------|------|------|------|
| 接入层 | `src/access/` | `cli.py` 命令行交互；`server.py` REST API | 可用 |
| 调度层 | `src/orchestration/` | `hierarchical.py`：Leader 拆解任务、调度成员 | 可用 |
| 执行层 | `src/execution/` | `agents/` ReAct Agent 工厂；`tools/` MCP + Skill 注册；`skills/` 加载器 | Agent 可用；**MCP/Skill 未接线**（见 5.1） |
| 存储层 | `src/storage/` | `memory/` 短期 + 长期记忆；`output/` 输出持久化 | **基本未接线**（见 5.2） |

---

## 二、CLI 运行链路（当前实际行为）

```text
scripts/run_agent.py
  └─ src.access.cli.main()
       ├─ check_api_key()                       # src/config.py
       ├─ asyncio.run(run_single_question(q))   # 单次提问分支
       │    └─ _chat_with_cleanup(              # 统一收尾，见 3.2(c)
       │           run_hierarchical(q))         # hierarchical.py:105
       │         └─ HierarchicalTeam().chat(q)  # hierarchical.py:91
       │              └─ Leader(ReActAgent)     # hierarchical.py:70
       │                   ├─ tool: invoke_researcher  → Research Agent
       │                   └─ tool: invoke_reviewer    → Review Agent
       └─ run_interactive()                     # 交互模式分支（同样走 _chat_with_cleanup）
```

关键事实：

- Leader 的 toolkit 只注册了 `invoke_researcher` / `invoke_reviewer` 两个工具（`hierarchical.py:67-68`）。
- `Research Agent` / `Review Agent` 由工厂函数创建时**未传 toolkit**，因此两个成员 Agent 自身没有任何工具。
- Leader 与成员 Agent 使用同一个模型（`DashScopeChatModel(model_name=LLM_MODEL)`）。
- 三个 Agent 现在都启用了 agentscope **内置历史自动压缩**（阈值 `MAX_MEMORY_TOKENS`），见 3.6。

---

## 三、修改清单

### 改动总览

| 组 | 主题 | 涉及文件 | 性质 |
|----|------|----------|------|
| 3.1 | dashscope 依赖下限 | `requirements.txt` | 修复（环境崩溃） |
| 3.2 | CLI 单次提问崩溃 + 连接泄漏 | `src/access/cli.py` | 修复（功能不可用） |
| 3.3 | 输出格式 + 工具调用异步化 | `src/orchestration/hierarchical.py` | 修复（功能不可用） |
| 3.4 | 可选参数类型标注 | `react_agent.py`、`agent_factory.py`、`short_term.py` | 修复（其中一处为运行时崩溃） |
| 3.5 | 只读 `sys_prompt` + `Literal` 模式 | `src/storage/memory/long_term.py` | 修复（潜伏运行时崩溃） |
| 3.6 | 删除自写滚动摘要，改用内置压缩 | `short_term.py`、`react_agent.py` | 重构 |

---

### 3.1 `requirements.txt:8-10` —— 依赖下限修正

```diff
 openai>=1.0.0
-dashscope>=1.14.0
+# 必须 >=1.25.0: agentscope 的多模态分支调用 dashscope.AioMultiModalConversation，
+# 该符号在 1.22.2/1.23.0/1.24.0 中均不存在 (首次出现于 1.25.0)。
+dashscope>=1.25.0
```

**原因**：`agentscope 1.0.18` 的元数据里 `Requires-Dist: dashscope` **没有版本下限**，pip 不会主动升级已装的旧版。原下限 `>=1.14.0` 允许安装缺少 `AioMultiModalConversation` 的版本，使用 VL 模型时必然抛
`AttributeError: module 'dashscope' has no attribute 'AioMultiModalConversation'`。

**验证**：逐个下载 wheel 核对 `dashscope/__init__.py`，符号出现的分界线为 `1.25.0`。

| 版本 | `AioMultiModalConversation` |
|------|------------------------------|
| 1.22.2（当时已装） | 不存在 |
| 1.23.0 / 1.24.0 | 不存在 |
| 1.25.0 / 1.26.0 / 1.27.6 | 存在 |

---

### 3.2 `src/access/cli.py` —— 接入层

#### (a) 修正导入：接入真实的异步 `run_hierarchical`

`cli.py:18`

```diff
-from src.orchestration.hierarchical import HierarchicalTeam
+from src.orchestration.hierarchical import HierarchicalTeam, run_hierarchical
```

**原因**：`run_single_question` 里 `await run_hierarchical(question)`，但该名字从未被导入。真正的实现是
`hierarchical.py:105` 的 `async def run_hierarchical(user_request: str) -> str`。

#### (b) 删除本地同名同步函数（**原始报错的根因**）

原文件在 `run_interactive` 与 `run_single_question` 之间有一个**本地同步副本**：

```python
def run_hierarchical(question: str):          # ← 已整块删除
    ...
    response = asyncio.run(team.chat(question))   # ← 在已运行的 loop 内再 run 一次
    print(f"\n回复:\n{response}")                 # ← 与 main() 重复打印
```

它造成两个叠加问题：

1. 同步函数没有 `return` → 返回 `None` → 外层 `await` 抛
   `TypeError: object NoneType can't be used in 'await' expression`；
2. 它内部又调一次 `asyncio.run()`，而外层 `main()` 已在运行事件循环 →
   `RuntimeError: asyncio.run() cannot be called from a running event loop`（被自身 `except` 吞掉后返回 `None`）。

它还遮蔽（shadow）了调度层那个正确的异步实现。删除后 `main()` 只打印一次回复。

#### (c) 新增统一收尾函数 `_chat_with_cleanup`，两个入口均接入

`cli.py:62-72`（新增）

```python
async def _chat_with_cleanup(awaitable: Awaitable[str]) -> str:
    """执行一次对话，并在退出前释放 dashscope 的连接池。..."""
    try:
        return await awaitable
    finally:
        await close_shared_aio_session()
```

接入点两处（`cli.py:7` 另新增 `from collections.abc import Awaitable`）：

```diff
 # run_interactive(), cli.py:52
-            response = asyncio.run(team.chat(question))
+            response = asyncio.run(_chat_with_cleanup(team.chat(question)))

 # run_single_question(), cli.py:75-77
 async def run_single_question(question: str) -> str:
     """单次提问。"""
-    return await run_hierarchical(question)
+    return await _chat_with_cleanup(run_hierarchical(question))
```

**原因**：dashscope 1.25+ 在 `dashscope/api_entities/aio_session.py` 中**为每个事件循环缓存一个
`aiohttp.ClientSession`**。项目每次调用都用 `asyncio.run()` 新建 loop，退出时 loop 关闭但 session 未释放，于是解释器退出时输出：

```text
Unclosed client session
Unclosed connector
Fatal error on SSL transport
RuntimeError: Event loop is closed
```

dashscope 提供官方释放入口 `close_shared_aio_session()`（关闭"当前 loop 对应的" session），在 loop 内、退出前调用即可。放在 `finally` 保证异常路径也释放。

**设计取舍**：释放逻辑只放在 `cli.py` 一处 —— 因为**是接入层拥有事件循环的生命周期**（`asyncio.run` 在接入层调用）。调度层因此不必感知 dashscope 的连接管理。

#### (d) 绕开 dashscope 自身错误的类型存根

`cli.py:11-13`

```python
# 从子模块导入: dashscope/__init__.pyi 把这个函数错误地声明成了同步函数，
# 会让 Pylance 误报 "None 并非 awaitable"。
from dashscope.api_entities.aio_session import close_shared_aio_session
```

**原因**：dashscope 自带 `py.typed` 与存根 `dashscope/__init__.pyi`，其中写的是
`def close_shared_aio_session() -> None: ...`（**错误**，实现其实是 `async def`）。Pylance 优先读 `.pyi`，于是把 `await close_shared_aio_session()` 判为"await 一个返回 None 的同步函数"。
而 `dashscope/api_entities/aio_session.py` **没有对应 `.pyi`**，从子模块导入即可让 Pylance 读到真实源码。属 dashscope 上游存根缺陷，上游修复后可改回顶层导入。

---

### 3.3 `src/orchestration/hierarchical.py` —— 调度层

#### (a) `chat()` 返回可读文本而非原始 content block

`hierarchical.py:100-102`

```diff
 msg = Msg(name="user", content=user_request, role="user")
 response = await self.leader(msg)
-        return response.content
+        return response.get_text_content() or ""
```

**原因**：AgentScope 1.x 的 `Msg.content` 是 content block 列表（`str | list[ContentBlock]`），不是字符串。原写法把列表直接当字符串返回，CLI 打印出 `[{'type': 'text', 'text': '...'}]`。
`Msg.get_text_content()` 会拼接所有 `text` 块，对已是 `str` 的 content 原样返回；无文本块时返回 `None`，故兜底 `or ""`，保证返回值确实是 `str`（与签名 `-> str` 一致）。

#### (b) 两个工具函数由同步改为异步（**修复了一个从未成功过的功能**）

`hierarchical.py:41-65`

```diff
-        def invoke_researcher(requirement: str) -> ToolResponse:
+        async def invoke_researcher(requirement: str) -> ToolResponse:
             """调用研究助手搜集资料。..."""
-            loop = asyncio.new_event_loop()
-            try:
-                result = loop.run_until_complete(
-                    self.researcher(Msg(name="leader", content=requirement, role="user"))
-                )
-                return ToolResponse(
-                    content=[TextBlock(type="text", text=result.get_text_content() or "")]
-                )
-            finally:
-                loop.run_until_complete(close_shared_aio_session())
-                loop.close()
+            result = await self.researcher(
+                Msg(name="leader", content=requirement, role="user")
+            )
+            return ToolResponse(
+                content=[TextBlock(type="text", text=result.get_text_content() or "")]
+            )
```

`invoke_reviewer`（`hierarchical.py:54-65`）做同样改造。

**原因**：AgentScope 的 `Toolkit` 对工具函数分两种处理（`agentscope/tool/_toolkit.py:972-994`）：

```python
if inspect.iscoroutinefunction(tool_func.original_func):
    res = await tool_func.original_func(**kwargs)   # 异步：在当前 loop 上 await
else:
    res = tool_func.original_func(**kwargs)         # 同步：直接在当前 loop 里调用
```

即同步工具函数是**在 Leader 正在运行的那个事件循环线程里被直接调用**的。而原实现又用
`asyncio.new_event_loop()` + `run_until_complete()` 在**同一线程内嵌套启动第二个循环** —— CPython 禁止跨循环嵌套（`base_events.py` 的 `Cannot run the event loop while another loop is running` 守卫）。

因此这两个工具**只要被 Leader 调用就必然失败**，改成 async 并被 `await` 是其唯一正确形态。修复前实测报错：

```text
RuntimeWarning: coroutine 'AgentBase.__call__' was never awaited
system: { ... "output": [{ "text": "Error: Cannot run the event loop while another loop is running" }] }
```

**附带影响**：消除了"每次工具调用新建 loop"的行为，因此 `hierarchical.py` 不再需要感知 dashscope 的 session 释放。

#### (c) 清理因 (b) 而失效的导入

```diff
-import asyncio
 ...
-# 从子模块导入: dashscope/__init__.pyi 把这个函数错误地声明成了同步函数，
-# 会让 Pylance 误报 "None 并非 awaitable"。
-from dashscope.api_entities.aio_session import close_shared_aio_session
```

`asyncio` 与 `close_shared_aio_session` 在该文件中已无引用点（释放职责统一收归 `cli.py`）。

---

### 3.4 可选参数类型标注（3 个文件）

Pylance 报「无法将"None"类型的表达式分配给"Toolkit"类型的参数」。这类报错的**正确修法是 `X | None = None`，而不是删掉默认值**。

#### (a) `src/execution/agents/react_agent.py:18-19`

```diff
-    toolkit: Toolkit = None,
-    max_iters: int = None,
+    toolkit: Toolkit | None = None,
+    max_iters: int | None = None,
```

#### (b) `src/execution/agents/agent_factory.py:11` 与 `:30`

```diff
-def create_research_agent(toolkit: Toolkit) -> ReActAgent:
+def create_research_agent(toolkit: Toolkit | None = None) -> ReActAgent:

-def create_review_agent(toolkit: Toolkit) -> ReActAgent:
+def create_review_agent(toolkit: Toolkit | None = None) -> ReActAgent:
```

**这里踩过一个坑**：该文件的 `= None` 默认值一度被删除（为了消掉同一个 Pylance 报错）。但删默认值只是把错误从函数定义**搬到了所有调用点**，而且让本来能跑的代码变成崩溃 —— `hierarchical.py:35-36` 是不带参数调用的：

```python
self.researcher = create_research_agent()      # TypeError!
self.reviewer = create_review_agent()
```

删除默认值后的实测结果：

```text
File "src\orchestration\hierarchical.py", line 35, in __init__
    self.researcher = create_research_agent()
TypeError: create_research_agent() missing 1 required positional argument: 'toolkit'
```

所以正确做法是恢复默认值 + 标注为可选。

#### (c) `src/storage/memory/short_term.py:17`

```diff
-    max_tokens: int = None,
+    max_tokens: int | None = None,
```

**原因**：该参数在 `short_term.py:28` 就是当"用配置默认值"的哨兵用的（`max_tokens = max_tokens or MAX_MEMORY_TOKENS`），`None` 有明确语义，标注必须可选。

**验证**：workspace 诊断由 4 个错误 → 0 个；`HierarchicalTeam()` 由 `TypeError` → 正常构造。

---

### 3.5 `src/storage/memory/long_term.py` —— 只读 `sys_prompt` 与 `Literal` 模式

#### (a) 只读 property 赋值（潜伏运行时崩溃）

```diff
     agent = ReActAgent(...)
-
-    if mode == "agent_control":
-        agent.sys_prompt = (            # ← AttributeError: can't set attribute
-            sys_prompt + "\n\n"
-            ...
-        )
 
     return agent
```

改为**在构造之前**拼装提示词（`long_term.py:89-97`）：

```python
if mode == "agent_control":
    # ReActAgent.sys_prompt 是只读 property (由 _sys_prompt + toolkit 技能提示动态复合)，
    # 系统提示词必须在构造时传入，不能构造后再赋值。
    sys_prompt = sys_prompt + "\n\n" + (
        "你可以使用以下工具来管理你的长期记忆:\n"
        ...
    )

agent = ReActAgent(..., sys_prompt=sys_prompt, ...)
```

**原因**：`ReActAgent.sys_prompt` 是**只读 property**（`_react_agent.py:366-373`），且是**动态派生**的 —— 它返回 `self._sys_prompt` 再拼上 `toolkit.get_agent_skill_prompt()`。实测 `ReActAgent.sys_prompt.fset is None`，赋值会抛
`AttributeError: can't set attribute 'sys_prompt'`。真正的存储字段是 `_sys_prompt`，只能由构造函数写入。

#### (b) `mode` 收紧为 `Literal`

```diff
-    mode: str = "static_control",
+    mode: Literal["agent_control", "static_control"] = "static_control",
```

**原因**：agentscope 的真实签名是
`long_term_memory_mode: Literal['agent_control', 'static_control', 'both'] = 'both'`，宽松的 `str` 会被 Pylance 判为不兼容。

> **当前文件状态提示**：我修改时该 `Literal` 含 `'both'`，现在磁盘上是 `Literal["agent_control", "static_control"]`（`'both'` 已被移除），但 docstring 第 84 行仍写着 `(static_control / agent_control / both)` —— 二者已不一致，见 5.6。

**验证**：诊断由 2 个错误 → 0；用 stub 记忆对象实跑 —— `agent_control` 构造成功且提示词含两个工具名，`static_control` 提示词保持原样，并复现了旧写法的 `AttributeError`。

---

### 3.6 删除自写滚动摘要，改用 agentscope 内置压缩（重构）

#### (a) 删除 `RollingSummaryMemory`

`src/storage/memory/short_term.py` —— 整块删除 56 行的 `RollingSummaryMemory(MemoryBase)`，并清理随之失效的东西：

| 项 | 处理 |
|----|------|
| `from agentscope.memory import InMemoryMemory, MemoryBase` | 去掉 `MemoryBase` |
| `from agentscope.message import Msg` | 整行删除（仅该类使用） |
| `from agentscope.model import DashScopeChatModel` | 整行删除（仅该类使用） |
| `from src.config import DASHSCOPE_API_KEY, LLM_MODEL, MAX_MEMORY_TOKENS` | 只保留 `MAX_MEMORY_TOKENS` |
| 模块 docstring「实现三种策略 … RollingSummary」 | 改为「两种策略」并注明滚动摘要改由内置能力承担 |

删除前已确认**全项目零引用**（`RollingSummaryMemory` / `create_short_term_memory` 等均无调用点）。

**为什么该删 —— 它不只是重复造轮子，而是不符合 `MemoryBase` 契约。** 用 agent 在 `reply()` 里真实发起的调用逐个探测：

| agent 的真实调用 | 出处 | 对 `RollingSummaryMemory` 的结果 |
|---|---|---|
| `add(msg)` | `_react_agent.py:396` | OK |
| `add(msg, marks="hint")` | `:506` / `:551` | **TypeError: unexpected keyword argument 'marks'** |
| `get_memory()` | `:531` | OK |
| `get_memory(exclude_mark="compressed")` | `:557`（**每轮都走**） | **TypeError: unexpected keyword argument 'exclude_mark'** |
| `delete_by_mark(mark="hint")` | `:566` | **NotImplementedError** |
| `update_messages_mark(new_mark="compressed")` | `:1123` | **NotImplementedError** |
| `size()` | — | **静默返回 None**（不是报错，是错值） |

基类契约是 `add(memories, marks=None, **kwargs)` 与
`get_memory(mark=None, exclude_mark=None, prepend_summary=True, **kwargs)`，而原实现是
`add(self, msg)` / `get_memory(self)`，缺 `marks`、`mark`、`exclude_mark`、`prepend_summary`。
`:557` 那处**无条件**传 `exclude_mark=`，所以只要把它接给任何 `ReActAgent`，第一次 `reply()` 就会炸。

另外：`MemoryBase` 虽然用了 `@abstractmethod`，但**抽象校验未生效**（其元类不是 `ABCMeta`：`MemoryBase.__abstractmethods__` 不存在，且该类能直接实例化、`size()` 还返回 `None`），所以缺失的方法被静默掩盖，直到真正被调用才暴露。

#### (b) 接入内置压缩

`src/execution/agents/react_agent.py:10, `45-54`

```diff
 from agentscope.memory import InMemoryMemory
+from agentscope.token import CharTokenCounter
 
-from src.config import DASHSCOPE_API_KEY, LLM_MODEL, MAX_REACT_ITERS
+from src.config import DASHSCOPE_API_KEY, LLM_MODEL, MAX_MEMORY_TOKENS, MAX_REACT_ITERS
```

```python
memory=InMemoryMemory(),
# 历史超过阈值时由 agentscope 自动压缩为结构化摘要，
# 替代原先自写的 RollingSummaryMemory (见 src/storage/memory/short_term.py)
compression_config=ReActAgent.CompressionConfig(
    enable=True,
    # 不用 OpenAITokenCounter: 它首次 count() 会下载 tiktoken 词表，
    # 该地址在本机不通会直接卡死。CharTokenCounter 纯本地按字符数估算。
    agent_token_counter=CharTokenCounter(),
    trigger_threshold=MAX_MEMORY_TOKENS,
    keep_recent=3,
),
```

**内置能力的工作方式**（`_react_agent.py`）：

| 环节 | 位置 | 行为 |
|------|------|------|
| 触发 | `:433-434` | 每次 `reply()` 开头自动 `await self._compress_memory_if_needed()` |
| 取未压缩消息 | `:1024-1025` | `get_memory(exclude_mark=COMPRESSED)` |
| 保留近期 | `:1046-1048` | 最近 `keep_recent` 条不参与压缩 |
| 阈值判断 | `:1062-1071` | `agent_token_counter.count(...) > trigger_threshold` |
| 生成摘要 | `:1095-1100` | 默认复用 agent 自己的模型 + 结构化 `SummarySchema` |
| 写回摘要 | `:1114` | `memory.update_compressed_summary(摘要)` |
| 打标记 | `:1121-1122` | `memory.update_messages_mark(COMPRESSED, msg_ids=[...])` |
| 读上下文 | `:557-560` | 构建 prompt 时排除 `COMPRESSED` 消息 |
| 摘要注入 | `_in_memory_memory.py:81-89` | 摘要作为一条 **user** 消息自动前置 |

**关键设计点**：摘要文本和"哪些消息已压缩"的标记都存在 **memory 对象内部**，压缩的驱动逻辑在 **agent 侧**。所以想要滚动摘要不需要继承 `MemoryBase`，用 `InMemoryMemory()` + `compression_config` 即可。

#### (c) `CharTokenCounter` 的取舍（重要）

首选方案本是 `OpenAITokenCounter`（与 `short_term.py:32` 的既有写法一致），但接入后验证脚本**卡死超过 60 秒**。根因：

- `OpenAITokenCounter.__init__` 只存 `model_name`，词表在 `count()` 里惰性加载：`tiktoken.encoding_for_model("gpt-4")`
- 首次调用会去 `openaipublic.blob.core.windows.net` **下载 BPE 词表**，而该地址在本机不通（详见第六节）
- tiktoken 的下载**没有超时机制** → 永久阻塞，只能 `taskkill`

改用 `CharTokenCounter`（纯本地）后 4 秒跑完。**代价**：其实现就是 `len(str(text))`，数的是**序列化后的字符数，不是 token 数**。因此 `trigger_threshold=4096` 的实际语义是"约 4096 个字符"。对中文而言与 token 量级接近（约 2500–4000 token），可接受，但语义确实变松了 —— 该 caveat 已写进代码注释。

---

## 四、验证记录

环境：conda env `llm_learn`，dashscope 1.27.6 / agentscope 1.0.18。

### 4.1 静态检查

- `get_diagnostics`：**全 workspace `No errors or warnings found`**（3.4 之前为 4 个错误，3.5 之前另有 2 个）。
- 期间发现 `get_diagnostics`/`grep_search` 对**未在编辑器中打开的文件**可能不返回结果，故关键行号改用 `findstr` 直接对磁盘核对。

### 4.2 端到端：纯对话路径

```bash
python scripts/run_agent.py --question "你好"
```

exit 0，输出为可读纯文本，**无任何 `Unclosed client session` / `Event loop is closed` 告警**：

```text
问题: 你好

Project Leader: 你好！我是你的项目负责人，负责协调和分配任务。……

回复:
你好！我是你的项目负责人，负责协调和分配任务。……
```

### 4.3 端到端：工具调用路径（覆盖 3.3(b)）

```bash
python scripts/run_agent.py --question "帮我搜集一下勾股定理的教学资料"
```

exit 0，完整走通 `Leader → invoke_researcher → Research Agent → Leader 汇总`：

```text
Project Leader: { "name": "invoke_researcher", "input": { "requirement": "搜集勾股定理的教学资料…" } }
Research Agent: 以下是我为您系统整理的**勾股定理**教学资料……   # 约 6KB 正文
system: { "type": "tool_result", "output": [ { "type": "text", "text": "以下是我为您系统整理的…" } ] }
Project Leader: 已为您系统整理并交付完整的勾股定理教学资料……
回复:
已为您系统整理并交付完整的勾股定理教学资料……
```

对比修复前的 `Error: Cannot run the event loop while another loop is running`，可确认 3.3(b) 生效。

### 4.4 运行时：内置记忆压缩（覆盖 3.6）

用真实工厂 `create_react_agent()` 构造 agent，再把阈值改为 1 强制触发：

```text
compression_config 已接入  : True
  enable                  : True
  trigger_threshold       : 4096 (MAX_MEMORY_TOKENS=4096)
  keep_recent             : 3
  token counter           : CharTokenCounter
  memory 类型             : InMemoryMemory
  memory 满足压缩契约     : True

压缩前消息数               : 4
内置压缩产出摘要           : True
摘要节选                   : <system-info>Here is a summary of your previous work | # Task Overview | ...
排除 compressed 后上下文   : 4 条
```

```text
INFO | _compress_memory_if_needed:1067 - Memory compression is triggered (254 > threshold 1) for agent VerifyAgent.
INFO | _compress_memory_if_needed:1126 - Finished compressing 1 messages in agent VerifyAgent.
```

4 条消息 + `keep_recent=3` → 压缩掉最早 1 条，结构化摘要写回 memory 并在读上下文时自动前置。该次运行 stderr 干净（脚本复用了 3.2(c) 的收尾模式）。

### 4.5 运行时：`long_term.py` 构造路径（覆盖 3.5）

用一个只实现 `record_to_memory` / `retrieve_from_memory` 的 stub 记忆对象（避免真写向量库）：

```text
agent_control  -> 构造成功
  提示词含 record_to_memory    : True
  提示词含 retrieve_from_memory: True
static_control -> 构造成功
  提示词保持原样              : True
  旧写法确实会崩 -> AttributeError: can't set attribute 'sys_prompt'
```

> 附带发现：`mode='agent_control'` 时 agentscope 会在构造期就把记忆方法注册成工具（`_react_agent.py:301-308`），所以 stub 必须实现这两个方法才能构造成功。

### 4.6 未覆盖的点（如实说明）

- `invoke_reviewer`（`hierarchical.py:54`）在上述测试中**未被 Leader 调用**（它自行判断无需审查）。代码结构与 `invoke_researcher` 一致、走同一修复路径，但**未经运行时验证**。建议用更长的任务促使 Leader 串上审查环节再验一次。
- `create_short_term_memory()`（`short_term.py:15`）、`create_long_term_memory()`、`create_agent_with_ltm()` 全项目无调用点，均为**未接线的死代码**，仅做了构造级验证（见 4.5）。

---

## 五、发现但**未修改**的问题（供决定是否处理）

按影响面排序。均为本次会话阅读代码时发现，**不在本次修改范围内**。

### 5.1 执行层：MCP 工具与 Skill 从未接入任何 Agent

- `src/access/cli.py:21 setup_toolkit()` **是死代码**：`run_interactive` 直接 `HierarchicalTeam()`，单轮路径走 `run_hierarchical`，两者都不调用它。因此 `cli.py:16` 导入的 `register_mcp_tools` / `register_skill_tools` / `close_mcp_client` 也只在这个死函数里被用到。
- `hierarchical.py:35-36` 创建成员 Agent 时**未传 toolkit** → `create_react_agent(toolkit=None)` 内部 `Toolkit()`，即空工具集。
- `src/access/server.py` 的 startup 里 `init_mcp(toolkit)` + `register_skill_tools(toolkit)` 注册到的是一个**局部变量**，既没保存也没交给 `HierarchicalTeam()`；而 `get_team()` 另起一个 team。注册结果被直接丢弃。

**净效果**：`configs/agent_config.yaml` 配置的 MCP 与 `skills/` 下的 Skill 对 Agent 完全不可达；前端显示的 `MCP: ...` 状态基本是装饰性的。

### 5.2 存储层：未接线，且多个配置项无人读取

- 删除 `RollingSummaryMemory` 后，`create_short_term_memory()`（`short_term.py:15`）、`create_long_term_memory()`（`long_term.py:23`）、`create_agent_with_ltm()`（`long_term.py:72`）**仍无任何调用点**。
- `src/storage/output/__init__.py` 只有一行注释，无实现。
- `react_agent.py:44` 直接硬编码 `memory=InMemoryMemory()`，因此以下 `src/config.py` 的配置**定义了但全程无人读取**：

| 配置项 | 位置 | 引用情况 |
|--------|------|----------|
| `MEMORY_STRATEGY` | `config.py:34` | **零引用** |
| `ENABLE_LONG_TERM_MEMORY` | `config.py:37` | **零引用** |
| `TEMPERATURE` | `config.py:30` | **零引用** |
| `BASE_URL` | `config.py:19` | **零引用** |
| `QDRANT_PATH` | `config.py:38` | 仅被未接线的 `long_term.py:53` 引用 |
| `MAX_MEMORY_TOKENS` | `config.py:35` | 已被 `react_agent.py:52` + `short_term.py:28` 使用 |

### 5.3 接入层：CLI 与 Server 的 MCP 注册逻辑重复且语义不同

`src/access/server.py:58 init_mcp()` 重新实现了一遍 `tool_manager.py:18 register_mcp_tools()` 的传输选择逻辑，但语义不同：server 是 try/except 回退，tool_manager 是 `raise ValueError`；且 tool_manager 只对 stdio 客户端 `connect()`。建议让 server 复用 `register_mcp_tools`。

### 5.4 `close_mcp_client` 只处理 stdio

`src/execution/tools/tool_manager.py:80-84`：仅对 `StdIOStatefulClient` 调 `close()`，`HttpStatelessClient` 被静默忽略（无 `else` 分支）。

### 5.5 ContextTruncation 分支会复现 tiktoken 卡死

`src/storage/memory/short_term.py:32` 构造的正是同一个计数器：

```python
return DashScopeChatFormatter(
    token_counter=OpenAITokenCounter(model_name="gpt-4"),   # 首次 count() 会去下载词表 → 卡死
    max_tokens=max_tokens,
)
```

目前该函数是死代码，但只要被启用就会复现第六节所述的挂死。改成 `CharTokenCounter()` 是一行的事，但属于另一个功能点，未擅自改动。

### 5.6 `long_term.py` 的 docstring 与 `Literal` 不一致

- 签名（`long_term.py:76`）：`Literal["agent_control", "static_control"]`
- docstring（`long_term.py:84`）：`记忆管理模式 (static_control / agent_control / both)`

`'both'` 被签名拒绝但文档仍在宣传。两者取其一即可（agentscope 本身支持 `'both'`）。

### 5.7 `mode="both"` 时不会追加记忆工具提示

agentscope 在 `agent_control` **和 `both`** 两种模式下都会自动注册 `record_to_memory` / `retrieve_from_memory` 工具（`_react_agent.py:289-296, 301-308`），但 `long_term.py:89` 只在 `mode == "agent_control"` 时追加提示词。若将来允许 `'both'`，工具可用但模型不知情，大概率不会调用。建议条件写成 `if mode in ("agent_control", "both"):`。

### 5.8 其它小问题

| 位置 | 问题 |
|------|------|
| `src/access/cli.py:80-83` | `main()` 解析了 `--interactive/-i` 但从不读取 `args.interactive`，行为只由 `--question` 是否存在决定 |
| `src/access/cli.py:10,16,17` | 未使用导入：`Msg`、`close_mcp_client`、`create_react_agent` |
| `src/access/server.py:10` | 未使用导入：`import asyncio` |
| `src/storage/memory/short_term.py:20` | 返回类型 `InMemoryMemory \| DashScopeChatFormatter` 把"记忆类"和"格式化器"混在一个注解里 |
| `mcp_servers/` | 缺 `__init__.py`（其余 `src/...` 包都有） |
| `scripts/run_mcp_server.py` | 与 `mcp_servers/web_search_server.py` 的 `__main__` 块重复 |
| `configs/agent_config.yaml` | 文件存在但无任何代码读取（实际配置来源是 `.env` + `src/config.py`） |
| `requirements.txt:4` | `agentscope>=0.1.0` 下限过松：代码使用 AgentScope 1.x API，与 0.x 完全不兼容，建议收紧到 `>=1.0.0` |

---

## 六、环境相关的坑（非仓库改动，但不改就跑不通）

### 6.1 dashscope 版本

`dashscope` 已由 1.22.2 **手动升级到 1.27.6**（在 `llm_learn` 环境）。`requirements.txt` 的 `>=1.25.0` 就是为固化这一要求。不在版本控制内，但换机器/重建环境时必须满足。

### 6.2 tiktoken 词表地址不可达（本机网络限制）

`https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken` 在**本机不通**，实测：

```text
curl --max-time 15 https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken
→ exit 28 (操作超时)
```

本地 tiktoken 缓存目录（`%TEMP%\data-gym-cache`）也是空的，因此任何触发 tiktoken 词表加载的代码路径都会**永久阻塞**（tiktoken 的下载无超时）。受影响的已知位置：3.6 中已规避（改用 `CharTokenCounter`）、5.5 中尚未处理。

**结论**：在本机环境下，`OpenAITokenCounter`（以及任何依赖 tiktoken 下载的编码器）不可用。

---

## 七、Review 建议的关注点

1. **3.3(b)** 影响最大 —— 它把一个"看起来能跑、实际必然报错"的工具调用路径改成真正可用。建议确认 async 改造是否符合你对"执行层"的设计意图（是否希望工具函数保持同步 API）。
2. **3.2(c)** 的职责划分：会话/连接释放放在接入层（因为 `asyncio.run` 在接入层），调度层不感知 dashscope 连接管理。若希望调度层自包含，可改为在 `run_hierarchical()` 内部收尾。
3. **3.6** 引入了记忆压缩这一新行为。请确认三点：① 阈值语义（`CharTokenCounter` 按字符计，非 token）；② `enable=True` 是否应改为由配置开关控制；③ `keep_recent=3` 是否合适。
4. **3.5(a)** 顺带说明一个 agentscope 的设计约束：`sys_prompt` 是只读派生属性，系统提示词只能在构造时确定 —— 后续若想动态改提示词，需要换别的机制。
5. **第五节** 中，5.1（MCP/Skill 未接线）与 5.2（存储层未接线 + 多个配置项无人读取）会让 README 中宣称的"执行层 = Agent + MCP + Skill"和"存储层 = 短期/长期记忆"与代码实际能力不符，建议优先决定是否补齐。5.5 是 3.6 同源的隐患，改动成本极低。
