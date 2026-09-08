"""
多Agent协作示例
演示 Research Agent、Review Agent 和 Summary Agent 的协同工作
"""

import asyncio
import os
from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit, ToolResponse
from agentscope.model import DashScopeChatModel
from agentscope.message import Msg, TextBlock
from agentscope.formatter import DashScopeChatFormatter


def create_research_agent():
    """创建研究助手 Agent"""
    toolkit = Toolkit()
    
    # 注册搜索工具
    def web_search(query: str) -> ToolResponse:
        """联网搜索。
        
        Args:
            query (str): 搜索关键词
        """
        print(f"  [Research] 正在搜索: {query}")
        return ToolResponse(
            content=[TextBlock(type="text", text=f"已搜索'{query}',找到相关资料。")]
        )
    
    toolkit.register_tool_function(web_search)
    
    agent = ReActAgent(
        name="Research Agent",
        sys_prompt="""你是一个专业的课程研究助理,专注于搜集和整理教学资料。

你的职责:
1. 使用搜索工具搜集相关资料
2. 筛选高质量的教学资源
3. 整理关键信息,形成结构化内容

注意:
- 确保信息来源可靠
- 结果要结构化、易于理解""",
        model=DashScopeChatModel(
            model_name="qwen-plus",
            api_key=os.environ.get("DASHSCOPE_API_KEY")
        ),
        toolkit=toolkit,
        formatter=DashScopeChatFormatter()
    )
    
    return agent


def create_review_agent():
    """创建质量审查 Agent"""
    agent = ReActAgent(
        name="Review Agent",
        sys_prompt="""你是一个严格的质量审查官,负责检查教学内容的质量。

审查维度:
1. **完整性**: 是否覆盖了所有必要的知识点
2. **准确性**: 内容是否准确,有无错误或误导性信息
3. **结构性**: 内容组织是否清晰,逻辑是否合理
4. **可读性**: 语言是否简洁,表达是否清晰

请给出具体的评分 (1-5分) 和改进建议。""",
        model=DashScopeChatModel(
            model_name="qwen-plus",
            api_key=os.environ.get("DASHSCOPE_API_KEY")
        ),
        toolkit=Toolkit(),  # 空工具箱,不需要工具
        formatter=DashScopeChatFormatter()
    )
    
    return agent


def create_summary_agent():
    """创建汇总整合 Agent"""
    agent = ReActAgent(
        name="Summary Agent",
        sys_prompt="""你是一个内容整合专家,擅长将多方信息整合为统一的输出。

你的职责:
1. 接收来自研究Agent的资料整理
2. 接收来自审查Agent的质量反馈
3. 根据质量反馈优化内容
4. 生成最终的、高质量的文档""",
        model=DashScopeChatModel(
            model_name="qwen-plus",
            api_key=os.environ.get("DASHSCOPE_API_KEY")
        ),
        toolkit=Toolkit(),
        formatter=DashScopeChatFormatter()
    )
    
    return agent


async def run_multi_agent_collaboration():
    """运行多Agent协作示例"""
    
    print("="*60)
    print("多Agent协作示例: 课程文档搜集与审查")
    print("="*60)
    
    # 1. 创建Agent实例
    print("\n[初始化] 创建 Research Agent、Review Agent 和 Summary Agent")
    research_agent = create_research_agent()
    review_agent = create_review_agent()
    summary_agent = create_summary_agent()
    
    # 2. 用户请求
    user_request = "为我准备一份关于'Transformer模型'的课程资料大纲,并审查质量。"
    print(f"\n[用户请求] {user_request}\n")
    
    # 3. Research Agent 搜集资料
    print("[阶段 1/3] Research Agent 开始搜集资料...")
    research_result = await research_agent(
        Msg(name="user", content=f"搜集关于'Transformer模型'的教学资料和最新研究进展。", role="user")
    )
    print(f"[Research Agent 完成]\n")
    
    # 4. Review Agent 审查质量
    print("[阶段 2/3] Review Agent 开始审查资料质量...")
    review_result = await review_agent(
        Msg(name="research", content=f"请审查以下Research Agent搜集的资料:\n\n{research_result.content}", role="user")
    )
    print(f"[Review Agent 完成]\n")
    
    # 5. Summary Agent 整合输出
    print("[阶段 3/3] Summary Agent 开始整合输出...")
    summary_result = await summary_agent(
        Msg(name="team", content=f"""
        研究资料:
        {research_result.content}
        
        审查反馈:
        {review_result.content}
        
        请根据以上信息,生成最终的课程资料大纲。
        """, role="user")
    )
    print(f"[Summary Agent 完成]\n")
    
    # 6. 输出最终结果
    print("="*60)
    print("最终输出")
    print("="*60)
    print(summary_result.content)
    print("="*60)


async def main():
    """主函数"""
    if not os.environ.get("DASHSCOPE_API_KEY"):
        print("错误: 请设置 DASHSCOPE_API_KEY 环境变量")
        exit(1)
    
    await run_multi_agent_collaboration()


if __name__ == "__main__":
    asyncio.run(main())
