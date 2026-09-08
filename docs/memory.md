# Memory 记忆管理模块文档

## 概述

Memory 记忆管理模块解决 Agent 的"失忆"问题。在没有记忆管理的情况下,Agent 每次开始新任务都像"失忆"一样,无法记住过去的经验、教训和知识。Memory 模块让 Agent 能够**积累经验、保存教训、快速召回历史信息**,从而实现持续改进。

## 为什么需要记忆管理?

### Agent 的"失忆"问题

```
第一次对话:
用户: "帮我搜集 Transformer 模型的资料"
Agent: [搜索资料,整理结果,花了很长时间]

第二次对话:
用户: "帮我搜集 BERT 模型的资料"
Agent: [重新搜索资料,重新整理,又花了很长时间]
       ← Agent 不记得上次搜集的资料和流程!
```

**问题表现**:
1. **重复劳动**: 每次任务都从零开始,不记得过去做过什么
2. **经验丢失**: 调试好的流程、踩过的坑,换个对话就忘了
3. **上下文丢失**: 长对话中的重要信息无法保存到后续对话

### 人类如何记忆?

人类解决问题时,会:
- **短期记忆**: 当前任务的上下文 (正在做什么)
- **长期记忆**: 积累的知识和经验 (以前做过什么)
- **主动记录**: 将重要信息记录下来 (笔记、文档)
- **快速召回**: 遇到类似问题时快速想起过去的经验

Memory 模块就是让 Agent 具备类似的能力。

## 记忆架构

```
┌──────────────────────────────────────────────────────────┐
│                    Memory 架构                            │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │               短期记忆 (Short-Term Memory)           │ │
│  │  - 当前对话上下文                                    │ │
│  │  - 工具调用历史                                      │ │
│  │  - 中间结果                                          │ │
│  │  - 自动维护 (Agent 框架内置)                         │ │
│  └─────────────────────────────────────────────────────┘ │
│                          ↕                               │
│  ┌─────────────────────────────────────────────────────┐ │
│  │               长期记忆 (Long-Term Memory)            │ │
│  │  - 跨会话经验                                        │ │
│  │  - 知识点和知识库                                    │ │
│  │  - 成功/失败案例                                     │ │
│  │  - 手动管理 (本项目实现)                             │ │
│  └─────────────────────────────────────────────────────┘ │
│                          ↕                               │
│  ┌─────────────────────────────────────────────────────┐ │
│  │             主动记忆管理 (Active Management)         │ │
│  │  - 决定保存什么 (Agent 自主判断)                     │ │
│  │  - 决定何时保存 (时机选择)                           │ │
│  │  - 如何组织和索引 (便于召回)                         │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

## 实现方案

### 1. 短期记忆 (Short-Term Memory)

短期记忆由 Agent 框架 (如 AgentScope) 内置管理,不需要单独实现。

**工作原理**:
- Agent 框架自动记录对话历史
- 自动记录工具调用和结果
- 在每次模型调用时传入完整上下文

```python
# AgentScope 自动管理短期记忆
agent = ReActAgent(
    name="Research Agent",
    model=model,
    toolkit=toolkit
)

# 框架自动记录:
# - 用户输入
# - Agent 的 Thought/Action/Observation
# - 工具调用结果
# - 最终回复
```

**限制**:
- 上下文窗口有限,对话过长会被截断
- 只在当前会话有效,会话结束就丢失

### 2. 长期记忆 (Long-Term Memory)

长期记忆需要手动实现,跨会话持久化保存。

#### 存储方案

**方案 A: 文件系统 (简单场景)**

```python
import json
import os
from datetime import datetime

class FileSystemMemory:
    def __init__(self, storage_path="./data/memory"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
    
    def save_memory(self, key: str, value: dict):
        """保存记忆到文件"""
        filepath = os.path.join(self.storage_path, f"{key}.json")
        memory_data = {
            "key": key,
            "value": value,
            "created_at": datetime.now().isoformat(),
            "accessed_count": 0
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(memory_data, f, ensure_ascii=False, indent=2)
    
    def load_memory(self, key: str) -> dict:
        """从文件加载记忆"""
        filepath = os.path.join(self.storage_path, f"{key}.json")
        if not os.path.exists(filepath):
            return None
        
        with open(filepath, 'r', encoding='utf-8') as f:
            memory_data = json.load(f)
        
        # 更新访问计数
        memory_data["accessed_count"] += 1
        memory_data["last_accessed"] = datetime.now().isoformat()
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(memory_data, f, ensure_ascii=False, indent=2)
        
        return memory_data["value"]
    
    def search_memories(self, query: str) -> list:
        """搜索相关记忆 (基于关键词匹配)"""
        memories = []
        for filename in os.listdir(self.storage_path):
            if filename.endswith('.json'):
                filepath = os.path.join(self.storage_path, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    memory_data = json.load(f)
                
                # 简单的关键词匹配
                if query.lower() in str(memory_data["value"]).lower():
                    memories.append(memory_data)
        
        # 按相关性和访问频率排序
        memories.sort(key=lambda m: m["accessed_count"], reverse=True)
        return memories
```

**方案 B: 向量数据库 (复杂场景)**

对于大量记忆,可以使用向量数据库实现语义搜索:

```python
# 使用 ChromaDB 等向量数据库
import chromadb

class VectorDBMemory:
    def __init__(self, collection_name="agent_memories"):
        self.client = chromadb.Client()
        self.collection = self.client.get_or_create_collection(collection_name)
    
    def save_memory(self, key: str, value: dict, embedding: list):
        """保存记忆 (带向量嵌入)"""
        self.collection.add(
            documents=[json.dumps(value, ensure_ascii=False)],
            embeddings=[embedding],
            ids=[key],
            metadatas=[{"created_at": datetime.now().isoformat()}]
        )
    
    def search_memories(self, query: str, query_embedding: list, n_results=5):
        """语义搜索相关记忆"""
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )
        return results
```

### 3. 主动记忆管理

让 Agent 自主判断何时保存记忆、保存什么。

#### 保存策略

```python
class ActiveMemoryManager:
    def __init__(self, memory_store):
        self.memory_store = memory_store
    
    def should_save(self, task_result: dict) -> bool:
        """判断是否应该保存这次经验"""
        # 规则 1: 任务耗时较长 (说明比较复杂,值得保存)
        if task_result.get("duration_seconds", 0) > 60:
            return True
        
        # 规则 2: 调用了多次工具 (说明流程复杂)
        if task_result.get("tool_call_count", 0) > 3:
            return True
        
        # 规则 3: 用户明确要求保存
        if task_result.get("user_request_save", False):
            return True
        
        # 规则 4: 遇到了错误并成功恢复 (重要教训)
        if task_result.get("errors_encountered", 0) > 0:
            return True
        
        return False
    
    def format_memory(self, task_result: dict) -> dict:
        """格式化记忆数据,便于存储和检索"""
        return {
            "task_type": task_result.get("task_type"),
            "tools_used": task_result.get("tools_used", []),
            "workflow": task_result.get("workflow_steps"),
            "errors": task_result.get("errors", []),
            "solution": task_result.get("solution"),
            "duration": task_result.get("duration_seconds"),
            "result_quality": task_result.get("result_quality")
        }
    
    async def manage_memory(self, task_result: dict):
        """完整的记忆管理流程"""
        if self.should_save(task_result):
            memory_data = self.format_memory(task_result)
            key = f"{task_result['task_type']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # 保存记忆
            self.memory_store.save_memory(key, memory_data)
            
            return f"已保存经验: {key}"
        
        return "无需保存"
```

#### 召回策略

在执行任务前,先检索相关记忆:

```python
async def recall_memories_before_task(user_request: str, memory_store):
    """任务开始前召回相关记忆"""
    
    # 从用户请求中提取关键词
    keywords = extract_keywords(user_request)
    
    # 搜索相关记忆
    relevant_memories = memory_store.search_memories(keywords)
    
    if relevant_memories:
        # 将记忆整合到系统提示词中
        memory_context = format_memories_for_prompt(relevant_memories)
        
        return f"""
        参考过去的经验:
        {memory_context}
        
        请基于以上经验执行当前任务。
        """
    
    return "无相关历史经验,请从零开始执行。"
```

## 典型应用场景

### 场景 1: 工具调用经验积累

```python
# 保存工具调用的成功经验
def save_tool_call_experience(tool_name: str, params: dict, result: str):
    """保存工具调用经验"""
    experience = {
        "tool": tool_name,
        "params": params,
        "result_summary": result[:200],  # 只保存摘要
        "success": True,
        "timestamp": datetime.now().isoformat()
    }
    
    key = f"tool_experience_{tool_name}_{datetime.now().strftime('%Y%m%d')}"
    memory_store.save_memory(key, experience)
```

### 场景 2: 错误教训记录

```python
# 保存遇到的错误和解决方案
def save_error_lesson(error_type: str, context: str, solution: str):
    """保存错误教训"""
    lesson = {
        "error_type": error_type,
        "context": context,
        "solution": solution,
        "timestamp": datetime.now().isoformat()
    }
    
    key = f"error_lesson_{error_type}_{datetime.now().strftime('%Y%m%d')}"
    memory_store.save_memory(key, lesson)
```

### 场景 3: 工作流模板保存

```python
# 保存成功执行的工作流
def save_workflow_template(task_type: str, steps: list):
    """保存工作流模板"""
    template = {
        "task_type": task_type,
        "steps": steps,
        "created_at": datetime.now().isoformat()
    }
    
    key = f"workflow_template_{task_type}"
    memory_store.save_memory(key, template)
```

## 最佳实践

### 1. 保存什么?

- **成功经验**: 有效的工作流程、高质量的输出
- **失败教训**: 遇到的错误、踩过的坑
- **工具经验**: 工具调用的最佳参数
- **用户偏好**: 用户的反馈和喜好

### 2. 何时保存?

- 任务完成后 (如果质量达标)
- 遇到并解决了错误
- 用户明确要求保存

### 3. 如何召回?

- **关键词匹配**: 简单场景,基于关键词搜索
- **语义搜索**: 复杂场景,使用向量数据库
- **时间排序**: 最近的记忆优先
- **频率排序**: 经常被引用的记忆更重要

## 故障排查

### 记忆膨胀 (存储过多)

**症状**: 记忆存储文件越来越多,检索变慢

**解决方案**:
- 设置记忆数量上限,超出时淘汰最旧的
- 定期清理低质量或过时的记忆
- 只保存摘要,不保存完整内容

### 记忆污染 (错误信息)

**症状**: Agent 基于错误的历史做出决策

**解决方案**:
- 为每条记忆添加质量标签
- 允许 Agent 更新或删除错误的记忆
- 定期检查记忆的准确性

## 相关资源

- [MemGPT: 让 LLM 拥有记忆管理](https://arxiv.org/abs/2310.08560)
- [LangChain Memory 文档](https://python.langchain.com/docs/modules/memory)
