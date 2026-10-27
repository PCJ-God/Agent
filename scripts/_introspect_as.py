import inspect

def sig(obj):
    try:
        return str(inspect.signature(obj))
    except Exception as e:
        return f"<no sig: {e}>"

def try_import(modname, names):
    try:
        return __import__(modname, fromlist=names)
    except Exception as e:
        print(f"IMPORT FAIL {modname}: {e}")
        return None

tool_mod = try_import("agentscope.tool", ["Toolkit"])
if tool_mod:
    print("==== agentscope.tool exports:", [n for n in dir(tool_mod) if not n.startswith("_")])
    Toolkit = tool_mod.Toolkit
    print("==== Toolkit.__init__:", sig(Toolkit.__init__))
    for m in dir(Toolkit):
        if not m.startswith("_") and ("register" in m.lower() or "add" in m.lower() or "set" in m.lower()):
            print("   Toolkit." + m + ":", sig(getattr(Toolkit, m)))

agent_mod = try_import("agentscope.agent", ["ReActAgent"])
if agent_mod:
    ReActAgent = agent_mod.ReActAgent
    print("==== ReActAgent.__init__:", sig(ReActAgent.__init__))
    print("==== ReActAgent methods:", [m for m in dir(ReActAgent) if not m.startswith("_")])

mem_mod = try_import("agentscope.memory", ["InMemoryMemory", "Mem0LongTermMemory"])
if mem_mod:
    for name in ["InMemoryMemory", "Mem0LongTermMemory"]:
        cls = getattr(mem_mod, name, None)
        if cls:
            print(f"==== {name}.__init__:", sig(cls.__init__))
            print(f"==== {name} methods:", [m for m in dir(cls) if not m.startswith("_")])

model_mod = try_import("agentscope.model", ["DashScopeChatModel"])
if model_mod:
    print("==== DashScopeChatModel.__init__:", sig(model_mod.DashScopeChatModel.__init__))

emb_mod = try_import("agentscope.embedding", ["DashScopeTextEmbedding"])
if emb_mod:
    print("==== DashScopeTextEmbedding.__init__:", sig(emb_mod.DashScopeTextEmbedding.__init__))

fmt_mod = try_import("agentscope.formatter", ["DashScopeChatFormatter"])
if fmt_mod:
    print("==== DashScopeChatFormatter.__init__:", sig(fmt_mod.DashScopeChatFormatter.__init__))

msg_mod = try_import("agentscope.message", ["Msg"])
if msg_mod:
    print("==== Msg.__init__:", sig(msg_mod.Msg.__init__))
    print("==== Msg fields:", getattr(msg_mod.Msg, "model_fields", "?"))
