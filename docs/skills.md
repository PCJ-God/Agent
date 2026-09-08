# Skill 技能固化模块文档

## 概述

Skill 技能固化模块将调试好的、验证过的工作流**封装为可复用的标准化流程**。就像软件开发中的"函数封装"一样,Skill 将复杂的 Prompt、工具调用、多Agent协作逻辑打包为一个简单的接口,让使用者无需关心内部实现细节。

## 为什么需要技能固化?

### 从 Prompt 到 Skill 的演进

**阶段 1: 临时 Prompt**
```python
# 每次都要写一大段提示词
prompt = """
你是一个文档审查专家。请审查以下文档的质量:
1. 检查完整性
2. 检查准确性
3. 检查结构性
4. 检查可读性

文档内容:
{document_content}
"""
```

问题:
- 每次使用都要复制粘贴大段提示词
- 提示词容易出错或遗漏
- 难以在团队间共享和复用

**阶段 2: 固化 Prompt 模板**
```python
def review_document(document_content):
    prompt = REVIEW_PROMPT_TEMPLATE.format(document_content=document_content)
    return llm.generate(prompt)
```

改进: 提示词被封装为模板
问题: 仍然只是单一的大模型调用,没有利用工具和Agent能力

**阶段 3: Skill (完整的工作流封装)**
```python
class DocumentReviewSkill:
    def __init__(self):
        self.research_agent = create_research_agent()
        self.review_agent = create_review_agent()
    
    async def execute(self, document_content):
        # 完整的审查流程
        research = await self.research_agent(...)
        review = await self.review_agent(...)
        return combine_results(research, review)
```

优势:
- ✅ 封装了完整的工具调用和Agent协作逻辑
- ✅ 统一的输入输出接口
- ✅ 可在不同场景和Agent间复用
- ✅ 内部流程经过验证,质量有保障

## 架构设计

### Skill 注册表

```python
class SkillRegistry:
    """技能注册表,管理所有可用技能"""
    
    def __init__(self):
        self.skills = {}
    
    def register_skill(self, name: str, skill_class):
        """注册一个技能"""
        self.skills[name] = skill_class
    
    def get_skill(self, name: str):
        """获取已注册的技能"""
        if name not in self.skills:
            raise ValueError(f"技能 '{name}' 未注册")
        return self.skills[name]()
    
    def list_skills(self) -> list:
        """列出所有可用技能"""
        return list(self.skills.keys())
```

### 技能定义标准

```python
from abc import ABC, abstractmethod

class BaseSkill(ABC):
    """所有技能的基类"""
    
    def __init__(self):
        self.name = self.__class__.__name__
        self.description = ""
        self.inputs = []
        self.outputs = []
    
    @abstractmethod
    async def execute(self, **kwargs):
        """执行技能的主要逻辑"""
        pass
    
    def validate_inputs(self, **kwargs):
        """验证输入参数"""
        for input_name in self.inputs:
            if input_name not in kwargs:
                raise ValueError(f"缺少必需参数: {input_name}")
    
    def format_output(self, result):
        """格式化输出结果"""
        return result
```

## 实现案例

### 1. 文档审查技能 (DocumentReviewSkill)

```python
class DocumentReviewSkill(BaseSkill):
    """文档审查技能: 搜集最佳实践 → 审查文档 → 生成建议"""
    
    def __init__(self):
        super().__init__()
        self.name = "document_review"
        self.description = "全面审查教学文档的质量,并提供改进建议"
        self.inputs = ["document_content", "topic"]
        self.outputs = ["review_report"]
        
        # 初始化内部Agent
        self.research_agent = create_research_agent()
        self.review_agent = create_review_agent()
        self.summary_agent = create_summary_agent()
    
    async def execute(self, document_content: str, topic: str):
        """执行文档审查流程"""
        
        # 步骤 1: 搜集相关教学最佳实践
        print("=== 搜集最佳实践 ===")
        research_result = await self.research_agent(
            Msg(name="user", 
                content=f"搜集'{topic}'主题的教学最佳实践和常见问题", 
                role="user")
        )
        
        # 步骤 2: 审查文档质量
        print("\n=== 审查文档质量 ===")
        review_result = await self.review_agent(
            Msg(name="user", 
                content=f"""
                请审查以下'{topic}'主题文档的质量:
                
                {document_content}
                
                参考以下教学最佳实践:
                {research_result.content}
                """, 
                role="user")
        )
        
        # 步骤 3: 生成改进建议
        print("\n=== 生成改进建议 ===")
        summary_result = await self.summary_agent(
            Msg(name="user", 
                content=f"""
                原文档: {document_content}
                研究资料: {research_result.content}
                审查反馈: {review_result.content}
                
                请生成具体的、可操作的改进建议。
                """, 
                role="user")
        )
        
        return {
            "review_report": summary_result.content,
            "research_data": research_result.content,
            "review_feedback": review_result.content
        }
```

### 2. 资料搜集技能 (ResearchSkill)

```python
class ResearchSkill(BaseSkill):
    """资料搜集技能: 多轮搜索 → 筛选 → 整理"""
    
    def __init__(self):
        super().__init__()
        self.name = "research"
        self.description = "系统化搜集和整理教学资料"
        self.inputs = ["topic", "focus_areas"]
        self.outputs = ["research_report", "resources_list"]
        
        self.research_agent = create_research_agent()
    
    async def execute(self, topic: str, focus_areas: list = None):
        """执行资料搜集流程"""
        
        # 构建搜索查询
        search_queries = self._build_search_queries(topic, focus_areas)
        
        # 并行搜索多个方面
        import asyncio
        tasks = []
        for query in search_queries:
            task = asyncio.create_task(
                self.research_agent(
                    Msg(name="user", content=f"搜索以下主题: {query}", role="user")
                )
            )
            tasks.append(task)
        
        # 等待所有搜索完成
        results = await asyncio.gather(*tasks)
        
        # 整理和去重
        organized_data = self._organize_results(results)
        
        return {
            "research_report": organized_data,
            "resources_list": self._extract_resources(results)
        }
    
    def _build_search_queries(self, topic: str, focus_areas: list) -> list:
        """构建搜索查询列表"""
        queries = [f"{topic} 基础知识 教学资料"]
        
        if focus_areas:
            for area in focus_areas:
                queries.append(f"{topic} {area} 最佳实践")
        
        return queries
    
    def _organize_results(self, results) -> str:
        """整理搜索结果"""
        # 实现去重、分类、排序逻辑
        return "整理后的资料"
    
    def _extract_resources(self, results) -> list:
        """提取资源链接"""
        return ["resource1_url", "resource2_url"]
```

### 3. 代码审查技能 (CodeReviewSkill)

```python
class CodeReviewSkill(BaseSkill):
    """代码审查技能: 静态分析 → 最佳实践对比 → 改进建议"""
    
    def __init__(self):
        super().__init__()
        self.name = "code_review"
        self.description = "审查代码质量,提供改进建议"
        self.inputs = ["code_content", "language"]
        self.outputs = ["review_report"]
        
        self.review_agent = create_review_agent()
    
    async def execute(self, code_content: str, language: str):
        """执行代码审查"""
        
        review_result = await self.review_agent(
            Msg(name="user", 
                content=f"""
                请审查以下 {language} 代码的质量:
                
                ```{language}
                {code_content}
                ```
                
                审查维度:
                1. 代码风格和规范
                2. 性能和效率
                3. 安全性和漏洞
                4. 可维护性和可读性
                5. 错误处理和边界情况
                
                请给出具体的问题和改进建议。
                """, 
                role="user")
        )
        
        return {"review_report": review_result.content}
```

## 使用方式

### 在 Agent 中集成技能

```python
from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit

# 创建 Agent
agent = ReActAgent(
    name="Teaching Assistant",
    sys_prompt="你是一个教学助手,拥有多种技能可以帮助完成教学任务。",
    model=model,
    toolkit=toolkit
)

# 将技能注册为工具
skill_registry = SkillRegistry()
skill_registry.register_skill("document_review", DocumentReviewSkill)
skill_registry.register_skill("research", ResearchSkill)
skill_registry.register_skill("code_review", CodeReviewSkill)

# Agent 可以像使用普通工具一样使用技能
def use_skill(skill_name: str, **kwargs):
    """调用技能的统一接口"""
    skill = skill_registry.get_skill(skill_name)
    skill.validate_inputs(**kwargs)
    result = asyncio.run(skill.execute(**kwargs))
    return skill.format_output(result)

# 示例: 调用文档审查技能
review_result = use_skill(
    "document_review",
    document_content="这是一份关于大模型原理的课程文档...",
    topic="大模型原理"
)
```

### 技能组合使用

```python
# 组合多个技能完成复杂任务
async def comprehensive_review(document_content, topic):
    # 1. 先搜集资料
    research_skill = skill_registry.get_skill("research")
    research_data = await research_skill.execute(topic=topic)
    
    # 2. 审查文档
    review_skill = skill_registry.get_skill("document_review")
    review_result = await review_skill.execute(
        document_content=document_content,
        topic=topic
    )
    
    # 3. 如果有代码,审查代码
    if "code" in document_content:
        code_skill = skill_registry.get_skill("code_review")
        code_review = await code_skill.execute(
            code_content=extract_code(document_content),
            language="python"
        )
    
    return {
        "research": research_data,
        "document_review": review_result,
        "code_review": code_review if "code" in document_content else None
    }
```

## 最佳实践

### 1. 技能设计原则

- **单一职责**: 每个技能只做一件事
- **清晰接口**: 输入输出要明确
- **可组合**: 技能之间可以互相调用
- **自包含**: 技能内部封装所有需要的逻辑

### 2. 技能命名规范

- 使用动词+名词格式: `document_review`, `research_topic`
- 名称要清晰表达技能的用途
- 避免过于通用的名称

### 3. 错误处理

```python
async def execute(self, **kwargs):
    try:
        self.validate_inputs(**kwargs)
        result = await self._do_execute(**kwargs)
        return self.format_output(result)
    except ValidationError as e:
        return {"error": f"输入验证失败: {str(e)}"}
    except ExecutionError as e:
        return {"error": f"执行失败: {str(e)}"}
```

## 相关资源

- [Qwen Code Skill 机制](https://github.com/QwenLM)
- [技能设计最佳实践](https://github.com/agentscope-ai/agentscope)
