"""
Skill 管理模块
支持本地 Skill 加载、社区 Skill 搜索/安装/更新
"""
import yaml
import json
import subprocess
import shutil
from pathlib import Path
from agentscope.tool import Toolkit


class SkillManager:
    """Skill 管理器。

    管理本地 Skill 和社区 Skill 的搜索、安装、更新。
    """

    def __init__(self, skills_dir: str = ""):
        """初始化 Skill 管理器。

        Args:
            skills_dir: 本地技能目录
        """
        from src.config import SKILLS_DIR
        self.skills_dir = Path(skills_dir) if skills_dir else SKILLS_DIR
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    # ── 本地 Skill 管理 ──

    def load_skill(self, skill_path: str) -> dict:
        """加载单个 Skill。

        Args:
            skill_path: SKILL.md 文件路径

        Returns:
            包含 frontmatter 和 body 的字典
        """
        path = Path(skill_path)
        content = path.read_text(encoding="utf-8")

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
        toolkit.register_agent_skill(str(Path(skill_path).parent))
        return skill_info

    def list_skills(self) -> list[dict]:
        """列出所有本地可用的 Skills。

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

    # ── 社区 Skill 管理 ──

    def find_skills(self, keyword: str) -> list[dict]:
        """搜索社区 Skill。

        使用 npx skills find 命令搜索社区 Skill。

        Args:
            keyword: 搜索关键词

        Returns:
            匹配的 Skill 列表
        """
        try:
            result = subprocess.run(
                ["npx", "skills", "find", keyword],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return self._parse_find_output(result.stdout)
        except FileNotFoundError:
            print("npx 未安装，请先安装 Node.js")
            return []
        except subprocess.TimeoutExpired:
            print("搜索超时")
            return []

    def install_skill(self, repo: str, skill_name: str = "") -> str:
        """安装社区 Skill。

        使用 npx skills add 命令安装社区 Skill 到本地。

        Args:
            repo: GitHub 仓库 (如 vercel-labs/agent-skills)
            skill_name: Skill 名称 (如 typescript-best-practices)

        Returns:
            安装后的 Skill 路径
        """
        cmd = ["npx", "skills", "add", repo]
        if skill_name:
            cmd.extend(["--skill", skill_name])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(self.skills_dir),
            )
            if result.returncode == 0:
                return f"Skill 已安装到: {self.skills_dir}"
            else:
                return f"安装失败: {result.stderr}"
        except FileNotFoundError:
            return "npx 未安装，请先安装 Node.js"
        except subprocess.TimeoutExpired:
            return "安装超时"

    def update_skills(self) -> str:
        """更新所有已安装的社区 Skill。

        Returns:
            更新结果信息
        """
        try:
            result = subprocess.run(
                ["npx", "skills", "update"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(self.skills_dir),
            )
            if result.returncode == 0:
                return "所有 Skill 已更新到最新版本"
            else:
                return f"更新失败: {result.stderr}"
        except FileNotFoundError:
            return "npx 未安装，请先安装 Node.js"
        except subprocess.TimeoutExpired:
            return "更新超时"

    def _parse_find_output(self, output: str) -> list[dict]:
        """解析 npx skills find 的输出。

        Args:
            output: 命令输出文本

        Returns:
            Skill 列表
        """
        skills = []
        for line in output.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("Install"):
                continue
            if "@" in line and "/" in line:
                parts = line.split("@", 1)
                if len(parts) == 2:
                    repo = parts[0].strip()
                    skill_name = parts[1].strip()
                    skills.append({
                        "repo": repo,
                        "name": skill_name,
                        "source": "community",
                    })
        return skills
