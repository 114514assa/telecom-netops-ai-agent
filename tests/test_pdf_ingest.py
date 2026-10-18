"""PDF infrastructure tests. CLI source is existing sanitized Demo fixture.
No claims of real production incidents or newly documented faults.
"""
import base64
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from app.services.pdf_ingest import (PdfIngestError, MAX_PDF_BYTES, extract_pdf_base64,
                                     extract_pdf_bytes)

FIXTURE = Path(__file__).parent / "fixtures" / "documented_interface_excerpt.pdf"


def test_pdf_extract_matches_existing_fixture():
    result = extract_pdf_bytes(FIXTURE.read_bytes())
    assert "GigabitEthernet0/0/15" in result["text"]
    assert "UP" in result["text"]
    assert result["pages"][0]["page"] == 1
    assert result["trust_level"] == "untrusted_user_document"
    assert result["truncated"] is False
    assert len(result["sha256"]) == 64


def test_pdf_base64_matches_direct_extract():
    raw = FIXTURE.read_bytes()
    assert extract_pdf_base64(base64.b64encode(raw).decode("ascii"))["sha256"] == extract_pdf_bytes(raw)["sha256"]


@pytest.mark.parametrize(
    "data, code",
    [
        pytest.param(b"not a PDF", "invalid_pdf", id="invalid_pdf_header"),
        pytest.param(b"", "file_size", id="empty_pdf"),
        pytest.param(b"X" * (MAX_PDF_BYTES + 1), "file_size", id="oversized_pdf"),
    ],
)
def test_pdf_rejects_invalid_input(data, code):
    with pytest.raises(PdfIngestError) as ex:
        extract_pdf_bytes(data)
    assert ex.value.code == code


def test_pdf_rejects_scanned_or_blank_page():
    writer = PdfWriter()
    writer.add_blank_page(width=400, height=400)
    buffer = BytesIO()
    writer.write(buffer)
    with pytest.raises(PdfIngestError) as ex:
        extract_pdf_bytes(buffer.getvalue())
    assert ex.value.code == "no_extractable_text"


def test_pdf_rejects_encryption():
    writer = PdfWriter()
    writer.add_page(PdfReader(str(FIXTURE)).pages[0])
    writer.encrypt("example-password")
    buf = BytesIO()
    writer.write(buf)
    with pytest.raises(PdfIngestError) as ex:
        extract_pdf_bytes(buf.getvalue())
    assert ex.value.code == "encrypted_pdf"


def test_invalid_base64_is_explicit():
    with pytest.raises(PdfIngestError) as ex:
        extract_pdf_base64("$bad$")
    assert ex.value.code == "invalid_base64"
