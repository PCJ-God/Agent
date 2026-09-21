"""用户自建技能：存储 CRUD + 跨用户隔离 + 物化 + 路径安全。

在**数据库副本**和**临时技能目录**上跑，绝不碰线上库与 data/skills。
用法: python scripts/check_user_skills.py
"""
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.execution.tools.skill_files import build_skill_map, read_skill_text  # noqa: E402
from src.storage.memory import session_store as store  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="userskills-"))
store.SESSIONS_DB = TMP / "test.db"        # 副本，不碰线上库
store.USER_SKILLS_DIR = TMP / "skills"     # 临时目录，不碰 data/skills
store._initialized = False                 # 让 init_db 在新路径上重跑迁移

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {name}" + (f" — {extra}" if extra else ""))
    else:
        failed += 1
        print(f"  [FAIL] {name}" + (f" — {extra}" if extra else ""))


def rejects(name, fn):
    """断言这次调用被拒（抛 SkillValidationError）。"""
    try:
        fn()
    except store.SkillValidationError as e:
        check(name, True, str(e)[:60])
        return
    check(name, False, "居然通过了")


print("=== 1) 迁移与建表 ===")
store.init_db()
cols = {r[1] for r in sqlite3.connect(store.SESSIONS_DB).execute("PRAGMA table_info(user_skills)")}
check("user_skills 表建好了", {"skill_id", "user_id", "slug", "body"} <= cols, str(sorted(cols)))

alice = store.create_user("alice")["user_id"]
bob = store.create_user("bob")["user_id"]

print()
print("=== 2) CRUD ===")
row = store.create_user_skill(
    alice, "code-review", "代码审查", "按清单审查 PR", "# 代码审查\n\n逐条检查。\n"
)
check("创建成功", bool(row.get("skill_id")) and row["slug"] == "code-review")
check("列表能看到它", [s["slug"] for s in store.list_user_skills(alice)] == ["code-review"])
check("列表带正文（前端编辑要预填，不能是空的）",
      store.list_user_skills(alice)[0]["body"] == "# 代码审查\n\n逐条检查。\n")
check("详情带正文", "逐条检查" in store.get_user_skill(alice, row["skill_id"])["body"])

print()
print("=== 3) 跨用户隔离（最关键的一组）===")
check("bob 的列表是空的", store.list_user_skills(bob) == [])
check("bob 拿 alice 的 skill_id 查不到", store.get_user_skill(bob, row["skill_id"]) is None)
check("bob 改不了 alice 的技能", store.update_user_skill(bob, row["skill_id"], name="hacked") is None)
check("bob 删不了 alice 的技能", store.delete_user_skill(bob, row["skill_id"]) is False)
check("alice 的技能确实没被动过", store.get_user_skill(alice, row["skill_id"])["name"] == "代码审查")

print()
print("=== 4) 字段校验 ===")
rejects("拒绝非法 slug（大写/空格）", lambda: store.create_user_skill(alice, "Bad Slug!", "x", "", "正文"))
rejects("拒绝 ../ 之类的 slug", lambda: store.create_user_skill(alice, "../etc", "x", "", "正文"))
rejects("拒绝重名 slug", lambda: store.create_user_skill(alice, "code-review", "另一个", "", "正文"))
rejects("拒绝空正文", lambda: store.create_user_skill(alice, "empty-body", "x", "", "   "))
rejects("拒绝超长正文", lambda: store.create_user_skill(alice, "too-long", "x", "", "x" * 30000))
rejects("拒绝空名称", lambda: store.create_user_skill(alice, "no-name", "  ", "", "正文"))

print()
print("=== 5) 物化（库 → 磁盘目录）===")
dirs = store.materialize_user_skills(alice)
check("物化出 1 个目录且名字是 slug", len(dirs) == 1 and Path(dirs[0]).name == "code-review")
md = Path(dirs[0]) / "SKILL.md"
check("SKILL.md 落盘", md.is_file())
text = md.read_text(encoding="utf-8")
check("frontmatter 的 name 等于 slug", 'name: "code-review"' in text, text.splitlines()[1])
check("正文进了文件", "逐条检查" in text)
check("重复物化是幂等的", sorted(store.materialize_user_skills(alice)) == sorted(dirs))

sk = build_skill_map(dirs)
check("技能读取器认得它", "code-review" in sk)
check("能通过读取器读到正文", "逐条检查" in read_skill_text(sk, "code-review"))

store.update_user_skill(alice, row["skill_id"], body="# 代码审查 v2\n\n改过了。\n")
dirs2 = store.materialize_user_skills(alice)
check("改正文后仍是同一个目录", dirs2 == dirs)
check("正文跟着更新", "改过了" in (Path(dirs2[0]) / "SKILL.md").read_text(encoding="utf-8"))

print()
print("=== 6) 删除要连盘上的目录一起清掉 ===")
check("删除成功", store.delete_user_skill(alice, row["skill_id"]) is True)
check("删完盘上目录立刻消失（不必等下次装配）", not Path(dirs[0]).exists())
check("删完列表为空", store.list_user_skills(alice) == [])
check("删完物化返回空", store.materialize_user_skills(alice) == [])

print()
print("=== 7) 路径安全：绕过入口直接往库里塞非法 slug ===")
with sqlite3.connect(store.SESSIONS_DB) as c:
    c.execute(
        "INSERT INTO user_skills (skill_id, user_id, slug, name, description, body, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("evil1", alice, "../../escape", "evil", "", "pwned", "t", "t"),
    )
check("物化时拦住了非法 slug（第二道闸）", store.materialize_user_skills(alice) == [])
check("没在临时目录之外写出东西", not (TMP.parent / "escape").exists())
check("恶意 user_id 被拒", store.materialize_user_skills("../../../etc") == [])

print()
print("=== 8) 数量上限 ===")
for i in range(store.MAX_SKILLS_PER_USER):
    store.create_user_skill(bob, f"bulk-{i}", f"批量 {i}", "", "正文")
check("批量建到上限", len(store.list_user_skills(bob)) == store.MAX_SKILLS_PER_USER)
rejects("超过上限被拒", lambda: store.create_user_skill(bob, "one-more", "多一个", "", "正文"))

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n结果: {'全部通过' if failed == 0 else str(failed) + ' 项失败'}   (共 {passed + failed} 项)")
sys.exit(1 if failed else 0)
