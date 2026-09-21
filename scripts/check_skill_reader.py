"""技能读取器的功能与安全测试。用法: python scripts/check_skill_reader.py

重点不是「能读到 SKILL.md」—— 而是**读不到别的东西**：第 2 节会真的造一个
指向本仓库 `.env`（里面有 DashScope key）的软链接去撞它。
"""
import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

#: 仓库根目录（本文件在 scripts/ 下），这样从哪个目录跑都能 import 到 src
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.execution.tools.skill_files import (  # noqa: E402
    SkillReadError,
    build_skill_map,
    make_skill_reader,
    read_skill_text,
)
from src.execution.tools.tool_manager import list_skill_dirs  # noqa: E402

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {name}" + (f" — {extra}" if extra else ""))
    else:
        failed += 1
        print(f"  [FAIL] {name}" + (f" — {extra}" if extra else ""))


def rejects(name, skills, skill_name, rel):
    """断言这次读取被拒，并打印它给出的原因。"""
    try:
        read_skill_text(skills, skill_name, rel)
    except SkillReadError as e:
        check(name, True, str(e)[:78])
        return
    check(name, False, "居然读成功了 —— 越权！")


def resp_text(resp):
    block = resp.content[0]
    return block["text"] if isinstance(block, dict) else getattr(block, "text", "")


print("=== 1) 真实部署的技能（/opt/agent/skills）===")
dirs = list_skill_dirs()
print("  技能目录:", [Path(d).name for d in dirs])
real = build_skill_map(dirs)
print("  可查的名字:", sorted(real))

txt = read_skill_text(real, "frontend-design")
check("能读到 frontend-design 的 SKILL.md", "Frontend Design" in txt, f"{len(txt)} 字符")
check("返回带行号", txt.lstrip().startswith("1: "))
check("ranges 只返回 3 行",
      len(read_skill_text(real, "frontend-design", ranges=[1, 3]).strip().splitlines()) == 3)
check("负数 ranges（最后 5 行）可用",
      len(read_skill_text(real, "frontend-design", ranges=[-5, -1]).strip().splitlines()) == 5)
check("技能名大小写不敏感", "Frontend Design" in read_skill_text(real, "Frontend-Design"))
rejects("未知技能名被拒", real, "no-such-skill", "SKILL.md")

print()
print("=== 2) 临时技能目录：模拟「用户自建技能」的各种逃逸 ===")
tmp = Path(tempfile.mkdtemp(prefix="skilltest-"))
slug = tmp / "my-skill"
slug.mkdir()
(slug / "SKILL.md").write_text(
    "---\nname: my-skill\ndescription: 测试用\n---\n\n# My Skill\n正文\n",
    encoding="utf-8",
)
(slug / "notes").mkdir()
(slug / "notes" / "ref.md").write_text("# 参考资料\n", encoding="utf-8")
(slug / "evil-link.md").symlink_to(ROOT / ".env")                # 软链接指向 .env
(slug / "big.md").write_text("x" * 300_000, encoding="utf-8")    # 超过 MAX_BYTES

sk = build_skill_map([str(slug)])
check("frontmatter 的 name 可查", "my-skill" in sk)
check("目录名也可查", slug.name in sk)
check("子目录里的资料文件可读", "参考资料" in read_skill_text(sk, "my-skill", "notes/ref.md"))

rejects("拒绝 ../ 穿越到 .env", sk, "my-skill", "../../.env")
rejects("拒绝多级 ../../ 穿越", sk, "my-skill", "../../../../etc/passwd")
rejects("拒绝绝对路径 /etc/passwd", sk, "my-skill", "/etc/passwd")
rejects("拒绝 Windows 盘符路径", sk, "my-skill", "C:\\Windows\\win.ini")
rejects("拒绝指向 .env 的软链接", sk, "my-skill", "evil-link.md")
rejects("拒绝把目录当文件读", sk, "my-skill", "notes")
rejects("拒绝超限的大文件", sk, "my-skill", "big.md")

print()
print("=== 3) 工具函数形态（模型实际看到的样子）===")
reader = make_skill_reader([str(slug)])
ok_text = resp_text(asyncio.run(reader("my-skill")))
check("正常调用返回 ToolResponse 且含正文", "# My Skill" in ok_text, f"{len(ok_text)} 字符")
bad_text = resp_text(asyncio.run(reader("my-skill", "../../.env")))
check("被拒时返回文本错误而不是抛异常", "读取失败" in bad_text, bad_text[:70].replace("\n", " "))
check("错误信息不泄露 .env 内容", "DASHSCOPE" not in bad_text and "sk-" not in bad_text)

print()
print("=== 4) 正面验证：.env 确实读不到 ===")
env = ROOT / ".env"
check("目标文件真的存在（否则这组测试是假的）", env.is_file(), str(env))
rejects("拿 .env 的绝对路径当技能名", sk, "/opt/agent/.env", "SKILL.md")
rejects("拿 .env 当技能名", sk, ".env", "SKILL.md")
rejects("技能名对但相对路径指向父目录的 .env", sk, "my-skill", "../.env")

shutil.rmtree(tmp, ignore_errors=True)
print(f"\n结果: {'全部通过' if failed == 0 else str(failed) + ' 项失败'}   (共 {passed + failed} 项)")
sys.exit(1 if failed else 0)
