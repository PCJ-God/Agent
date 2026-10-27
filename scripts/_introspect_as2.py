import inspect
from agentscope.tool import Toolkit, ToolResponse
from agentscope.agent import ReActAgent
from agentscope import tool as tool_mod

print("==== ToolResponse.__init__:", inspect.signature(ToolResponse.__init__))
print("==== ToolResponse methods:", [m for m in dir(ToolResponse) if not m.startswith("_")])

# 内置工具函数的返回值样例（view_text_file）
fn = getattr(tool_mod, "view_text_file", None)
if fn:
    print("==== view_text_file sig:", inspect.signature(fn))

# 看一个内置函数的源码片段，确认它 return 什么
import textwrap
src = inspect.getsource(fn)
print("==== view_text_file source (tail):")
print("\n".join(textwrap.dedent(src).splitlines()[-12:]))

print("\n==== ReActAgent.reply:", inspect.signature(ReActAgent.reply))
print("==== ReActAgent.reply is coroutine:", inspect.iscoroutinefunction(ReActAgent.reply))
print("==== ReActAgent.__call__:", inspect.signature(ReActAgent.__call__))
print("==== ReActAgent.__call__ is coroutine:", inspect.iscoroutinefunction(ReActAgent.__call__))
print("==== ReActAgent.set_msg_queue_enabled:", inspect.signature(ReActAgent.set_msg_queue_enabled))
print("==== ReActAgent.supported_hook_types:", ReActAgent.supported_hook_types)
print("==== ReActAgent.observe:", inspect.signature(ReActAgent.observe))
