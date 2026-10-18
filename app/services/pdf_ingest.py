"""Read-only extraction of user-supplied, text-based PDF documents.

No network access, disk paths, OCR, LLM execution, or trust promotion. Extracted
content is untrusted user data. Production needs an isolated PDF parsing worker.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
from io import BytesIO
from typing import Any

MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 20
MAX_EXTRACTED_CHARS = 30_000


class PdfIngestError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def extract_pdf_bytes(data: bytes) -> dict[str, Any]:
    """Extract bounded text with page provenance; never interpret as facts or instructions."""
    if not data or len(data) > MAX_PDF_BYTES:
        raise PdfIngestError("file_size", "PDF 必须为非空文件，且不超过 5 MiB")
    if not data.lstrip(b"\xef\xbb\xbf\x00\r\n\t ").startswith(b"%PDF-"):
        raise PdfIngestError("invalid_pdf", "文件没有有效的 PDF 文件头")

    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise PdfIngestError("encrypted_pdf", "不接受加密 PDF，请提交脱敏后的可读取文件")
        count = len(reader.pages)
        if count == 0 or count > MAX_PDF_PAGES:
            raise PdfIngestError("page_count", "PDF 页数必须在 1–20 页之间")
        pages: list[dict[str, Any]] = []
        remain = MAX_EXTRACTED_CHARS
        truncated = False
        for number, page in enumerate(reader.pages, start=1):
            # pypdf extracts native text only; images/scans are not interpreted.
            content = (page.extract_text() or "").replace("\x00", "")
            if len(content) > remain:
                truncated = True
                content = content[:remain]
            if content.strip():
                pages.append({"page": number, "text": content})
            remain -= len(content)
            if remain == 0 and number < count:
                truncated = True
                break
    except PdfIngestError:
        raise
    except (PdfReadError, ValueError, KeyError, IndexError, TypeError, OSError, NotImplementedError, OverflowError) as exc:
        raise PdfIngestError("parse_failed", "PDF 文档结构无法安全解析") from exc
    if not pages:
        raise PdfIngestError("no_extractable_text", "没有提取到可用文本：扫描件/图片型 PDF 暂不支持 OCR")
    text = "\n".join(item["text"] for item in pages)
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "page_count": count,
        "extracted_page_count": len(pages),
        "truncated": truncated,
        "char_count": len(text),
        "pages": pages,
        "text": text,
        "trust_level": "untrusted_user_document",
        "note": "仅提取用户提供的 PDF 文本；未验证真实性、时效或来源，不会自动成为网络诊断事实。",
    }


def extract_pdf_base64(value: str) -> dict[str, Any]:
    """Bounded MCP byte transport: avoids arbitrary file paths and file-write tools."""
    if not isinstance(value, str) or len(value) > ((MAX_PDF_BYTES + 2) // 3) * 4 + 16:
        raise PdfIngestError("base64_size", "Base64 PDF 数据长度超限")
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise PdfIngestError("invalid_base64", "PDF Base64 编码无效") from exc
    return extract_pdf_bytes(raw)
