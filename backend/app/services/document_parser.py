"""文档解析:把上传字节按类型抽取为纯文本。

MVP 支持 txt / md(直接解码)与 pdf(pypdf 逐页抽取)。
"""

import io

SUPPORTED_TYPES = {"txt", "md", "pdf"}


def detect_file_type(filename: str) -> str:
    """从文件名后缀推断类型,归一为 txt / md / pdf。"""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in {"md", "markdown"}:
        return "md"
    if ext == "pdf":
        return "pdf"
    return "txt"  # 其余按纯文本处理


def parse(data: bytes, file_type: str) -> str:
    """按类型解析字节为文本(出口统一清洗,去除 NUL 等 PostgreSQL 无法入库的字符)。"""
    if file_type == "pdf":
        text = _parse_pdf(data)
    else:
        # txt / md:尝试 utf-8,退回 gbk,最终忽略不可解码字节
        text = _decode_text(data)
    return _sanitize(text)


def _decode_text(data: bytes) -> str:
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _sanitize(text: str) -> str:
    """剔除 NUL 字节(\\x00):PostgreSQL text/varchar 不允许,否则入库报
    invalid byte sequence for encoding "UTF8": 0x00。PDF 抽取常见。"""
    return text.replace("\x00", "")


def _parse_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)
