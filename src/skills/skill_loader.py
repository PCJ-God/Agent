"""
Skill 加载器
从 SKILL.md 文件加载技能定义，支持渐进式披露
"""
import yaml
from pathlib import Path
from agentscope.tool import Toolkit


class SkillLoader:
    """Skill 加载器。

    从 SKILL.md 文件中读取 YAML frontmatter 和 Markdown 正文，
    支持渐进式披露 (只加载 description，按需加载全文)。
    """

    def __init__(self, skills_dir: str = None):
        """初始化 Skill 加载器。

        Args:
            skills_dir: 技能目录路径
        """
        from src.config import SKILLS_DIR
        self.skills_dir = Path(skills_dir) if skills_dir else SKILLS_DIR

    def load_skill(self, skill_path: str) -> dict:
        """加载单个 Skill。

        Args:
            skill_path: SKILL.md 文件路径

        Returns:
            包含 frontmatter 和 body 的字典
        """
        path = Path(skill_path)
        content = path.read_text(encoding="utf-8")

        # 解析 YAML frontmatter
        parts = content.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"无效的 SKILL.md 格式: {skill_path}")

        frontmatter = yaml.safe_load(parts[1])
        body = parts[2].strip()

        return {
            "name": frontmatter.get("name", path.parent.name),
            "description": frontmatter.get("description", ""),
            "body": body,
            "frontmatter": frontmatter,
        }

    def register_skill(self, toolkit: Toolkit, skill_path: str) -> dict:
        """注册 Skill 到 Toolkit。

        AgentScope 的 register_agent_skill 会自动从 SKILL.md 的
        frontmatter 中提取 name 和 description，注入到系统提示中。

        Args:
            toolkit: 工具箱实例
            skill_path: SKILL.md 文件路径

        Returns:
            Skill 信息字典
        """
        skill_info = self.load_skill(skill_path)

        # 注册 Skill (渐进式披露: 只注入 description)
        toolkit.register_agent_skill(str(Path(skill_path).parent))

        return skill_info

    def list_skills(self) -> list[dict]:
        """列出所有可用的 Skills。

        Returns:
            所有 Skill 的信息列表
        """
        skills = []
        for skill_dir in self.skills_dir.iterdir():
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    try:
                        skill_info = self.load_skill(str(skill_file))
                        skills.append(skill_info)
                    except Exception as e:
                        print(f"加载 Skill 失败 {skill_dir.name}: {e}")

        return skills
