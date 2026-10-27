"""问题理解层（格式归一化）：把任意输入转成「规范文字 + 元数据」。

- 纯文本（md/txt/json/csv/log）：原样解码
- docx：python-docx 抽段落 + 表格文字
- pdf：pymupdf 抽文字层；扫描版转图片走 OCR
- 图片（png/jpg/jpeg/webp）：DashScope 视觉 OCR（qwen-vl-ocr）
解析后文字超 MAX_TEXT_CHARS 抛 ValueError（对应「文档内容过长」）。
"""
from __future__ import annotations

import base64
from io import BytesIO

import fitz  # pymupdf
import httpx

from app.config import DASHSCOPE_API_KEY, MAX_TEXT_CHARS, OCR_MODEL

OCR_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

TEXT_EXTS = (".md", ".txt", ".json", ".csv", ".log")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def parse(filename: str, content: bytes) -> tuple[str, dict]:
    """解析文档为纯文本。返回 (文字, 元数据)；超长/不支持抛 ValueError。"""
    lower = filename.lower()
    if lower.endswith(TEXT_EXTS):
        text = content.decode("utf-8", errors="ignore")
        meta = {"filename": filename, "type": "text"}
    elif lower.endswith(".docx"):
        text = _parse_docx(content)
        meta = {"filename": filename, "type": "docx"}
    elif lower.endswith(".pdf"):
        text = _parse_pdf(content)
        meta = {"filename": filename, "type": "pdf"}
    elif lower.endswith(IMAGE_EXTS):
        text = _ocr_image(content)
        meta = {"filename": filename, "type": "image"}
    else:
        raise ValueError(f"不支持的文件类型: {lower}")

    text = text.strip()
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"文档内容过长（超过 {MAX_TEXT_CHARS} 字符），请拆分或精简后重试")
    return text, meta


def _parse_docx(content: bytes) -> str:
    import docx

    doc = docx.Document(BytesIO(content))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    return "\n".join(parts)


def _parse_pdf(content: bytes) -> str:
    doc = fitz.open(stream=content, filetype="pdf")
    parts = [page.get_text() for page in doc]
    text = "\n".join(parts).strip()
    if text:
        return text
    # 扫描版 PDF：逐页渲染成图片 OCR
    ocr_parts = []
    for page in doc:
        pix = page.get_pixmap(dpi=150)
        ocr_parts.append(_ocr_image(pix.tobytes("png")))
    return "\n".join(ocr_parts)


def _ocr_image(content: bytes) -> str:
    b64 = base64.b64encode(content).decode()
    payload = {
        "model": OCR_MODEL,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [{"image": f"data:image/png;base64,{b64}"}],
                }
            ]
        },
    }
    with httpx.Client(timeout=120) as client:
        resp = client.post(
            OCR_URL,
            headers={
                "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    choices = data.get("output", {}).get("choices", [])
    if not choices:
        return ""
    content = choices[0].get("message", {}).get("content", "")
    if isinstance(content, list):
        return "".join(c.get("text", "") for c in content if isinstance(c, dict))
    return content or ""
