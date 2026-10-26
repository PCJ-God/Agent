"""把课程 Notebook 批量转为 Markdown（nbconvert），供知识库摄入。

用法: python _nb2md.py [输出目录]
- 只导出 Markdown 单元（教学文字），跳过代码单元
- 剔除 course_core 下的 Notebook（数据分析实战，非 ACP 考点）
- 清理 HTML 标签/注释/图片链接，保留纯文字
"""
import html as html_lib
import re
import sys
import warnings
from pathlib import Path

import nbformat
from nbconvert import MarkdownExporter

warnings.filterwarnings("ignore")  # 忽略 nbformat 的 MissingIDField 警告

COURSE_ROOT = Path(r"E:\github项目经历\大模型ACP认证\aliyun_acp_learning\大模型ACP认证教程")
OUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("_nb_md")


def clean_html(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)   # 去注释（含重复的备选内容）
    text = re.sub(r"<br\s*/?>", "\n", text)                    # <br> -> 换行
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)             # 去其余标签，保留文字
    text = html_lib.unescape(text)                             # &amp; 等实体还原
    text = re.sub(r"[ \t]+\n", "\n", text)                     # 行尾空白
    text = re.sub(r"\n{3,}", "\n\n", text)                     # 压缩空行
    return text.strip()


exporter = MarkdownExporter(exclude_code_cell=True)

converted = []
for nb_path in sorted(COURSE_ROOT.rglob("*.ipynb")):
    rel = nb_path.relative_to(COURSE_ROOT)
    if rel.parts[0] == "course_core":        # 剔除非考点 Notebook
        continue
    out_name = str(rel).replace("\\", "_").replace("/", "_").replace(".ipynb", ".md")
    nb = nbformat.read(str(nb_path), as_version=4)
    body, _ = exporter.from_notebook_node(nb)
    body = clean_html(body)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / out_name).write_text(body, encoding="utf-8")
    converted.append((out_name, len(body)))

for name, size in converted:
    print(f"{size:>7}  {name}")

print(f"\n共 {len(converted)} 篇，输出目录: {OUT_DIR}")
