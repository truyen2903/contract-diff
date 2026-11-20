from io import BytesIO

import pdfplumber.page
import pytest
from fastapi import HTTPException
from pdfplumber.utils.exceptions import PdfminerException

from app.core import config
from app.extractors import pdf_extractor
from app.extractors.pdf_extractor import InvalidPDFError, PDFPageLimitError
from app.services import document_service
from app.services.comparison_service import compare_document, compare_text
from app.services.document_service import extract_document, validate_pdf_stream


def extract_pdf(file_stream, max_pages=config.MAX_PDF_PAGES):
    return pdf_extractor.extract_pdf(file_stream, max_pages)


def assert_http_error(error_info, status_code, error_code):
    assert error_info.value.status_code == status_code
    assert error_info.value.detail["error_code"] == error_code


# ── compare_text ─────────────────────────────────────────

def test_compare_text_identical():
    result = compare_text("Bên A", "Bên A")

    assert result["is_identical"] is True
    assert result["is_token_identical"] is True
    assert result["changes"] == []


def test_compare_text_whitespace_only_difference():
    result = compare_text("a b", "a  b")

    assert result["is_identical"] is False
    assert result["is_token_identical"] is True
    assert result["changes"] == []


def test_compare_text_token_difference():
    result = compare_text("a b", "a c")

    assert result["is_identical"] is False
    assert result["is_token_identical"] is False
    assert len(result["changes"]) == 1


# ── extract_pdf ──────────────────────────────────────────

def test_extract_pdf_reads_every_page(make_pdf):
    pages = extract_pdf(BytesIO(make_pdf(["Hello", "World"])))

    assert [page["text"] for page in pages] == ["Hello", "World"]
    assert [page["page_number"] for page in pages] == [1, 2]


def test_extract_pdf_marks_empty_page(make_pdf):
    pages = extract_pdf(BytesIO(make_pdf(["Hello", ""])))

    assert pages[1]["warnings"] == ["EMPTY_TEXT"]


def test_extract_pdf_accepts_owner_only_encryption(make_pdf):
    pages = extract_pdf(BytesIO(make_pdf(["Hello secret"], encryption="owner_only")))

    assert pages[0]["text"] == "Hello secret"


@pytest.mark.parametrize("data", [
    b"%PDF-1.4\nnot a document",
    b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog",
], ids=["garbage", "truncated"])
def test_extract_pdf_rejects_broken_pdf(data):
    with pytest.raises(InvalidPDFError):
        extract_pdf(BytesIO(data))


def test_extract_pdf_rejects_user_password(make_pdf):
    with pytest.raises(InvalidPDFError):
        extract_pdf(BytesIO(make_pdf(["secret"], encryption="user_password")))


def test_extract_pdf_rejects_zero_pages(make_pdf):
    with pytest.raises(InvalidPDFError):
        extract_pdf(BytesIO(make_pdf([])))


@pytest.mark.parametrize("page_extra", [
    b"/CropBox [0 0 (x) 100]",
    b"/Rotate /Invalid",
    b"/CropBox [0 0]",
], ids=["non-number-box", "bad-rotate", "short-box"])
def test_extract_pdf_rejects_malformed_page(make_pdf, page_extra):
    with pytest.raises(InvalidPDFError):
        extract_pdf(BytesIO(make_pdf(["Hello"], page_extra=page_extra)))


def test_extract_pdf_page_limit(make_pdf):
    assert len(extract_pdf(BytesIO(make_pdf(["x"] * 3)), max_pages=3)) == 3

    with pytest.raises(PDFPageLimitError):
        extract_pdf(BytesIO(make_pdf(["x"] * 4)), max_pages=3)


@pytest.mark.parametrize("key", [b"/O", b"/U", b"/P"])
def test_extract_pdf_rejects_broken_encryption_dictionary(make_pdf, key):
    data = make_pdf(["x"], encryption="owner_only").replace(key + b" ", b"/Q ")

    with pytest.raises(InvalidPDFError):
        extract_pdf(BytesIO(data))


def test_extract_pdf_page_limit_does_not_build_every_page(make_pdf, monkeypatch):
    built = []
    original_init = pdfplumber.page.Page.__init__

    def counting_init(self, *args, **kwargs):
        built.append(1)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(pdfplumber.page.Page, "__init__", counting_init)

    with pytest.raises(PDFPageLimitError):
        extract_pdf(BytesIO(make_pdf(["x"] * 50)), max_pages=3)
    assert built == []


def test_extract_pdf_null_only_page_is_also_empty(monkeypatch, make_pdf):
    monkeypatch.setattr(pdfplumber.page.Page, "extract_text", lambda self, **kwargs: " \x00 ")

    pages = extract_pdf(BytesIO(make_pdf(["x"])))

    assert pages[0]["warnings"] == ["NULL_CHARACTER", "EMPTY_TEXT"]


# Lỗi phía server không được dán nhãn thành "PDF hỏng" (400).

def test_extract_pdf_does_not_hide_io_error_while_counting(make_pdf):
    class FailingStream(BytesIO):
        def read(self, *args):
            raise OSError("disk error")

    with pytest.raises(OSError):
        extract_pdf(FailingStream(make_pdf(["x"])))


@pytest.mark.parametrize("error", [OSError("disk error"), MemoryError()])
def test_extract_pdf_does_not_hide_server_error_wrapped_by_pdfplumber(make_pdf, monkeypatch, error):
    # pdfplumber.open bọc lỗi trong PdfminerException; bước đếm trang dùng pdfminer trực tiếp.
    def failing_document(*args, **kwargs):
        raise error

    monkeypatch.setattr("pdfplumber.pdf.PDFDocument", failing_document)

    with pytest.raises(PdfminerException) as error_info:
        extract_pdf(BytesIO(make_pdf(["x"])))
    assert error_info.value.args[0] is error


def test_extract_pdf_does_not_hide_memory_error_while_extracting(make_pdf, monkeypatch):
    def failing_extract_text(self, **kwargs):
        raise MemoryError()

    monkeypatch.setattr(pdfplumber.page.Page, "extract_text", failing_extract_text)

    with pytest.raises(MemoryError):
        extract_pdf(BytesIO(make_pdf(["x"])))


# ── validate_pdf_stream / extract_document ───────────────

def test_validate_pdf_stream_rewinds(make_pdf):
    stream = BytesIO(make_pdf(["x"]))
    stream.seek(3)

    validate_pdf_stream("a.pdf", stream)

    assert stream.tell() == 0


@pytest.mark.parametrize("data", [b"", b"hello", b"JUNK%PDF-1.4"], ids=["empty", "text", "prefix"])
def test_validate_pdf_stream_rejects_non_pdf(data):
    with pytest.raises(HTTPException) as error_info:
        validate_pdf_stream("a.pdf", BytesIO(data))

    assert_http_error(error_info, 400, "INVALID_OR_ENCRYPTED_PDF")
    assert "a.pdf" in error_info.value.detail["detail"]


def test_validate_pdf_stream_size_limit(monkeypatch):
    monkeypatch.setattr(document_service, "MAX_UPLOAD_FILE_BYTES", 10)

    validate_pdf_stream("a.pdf", BytesIO(b"%PDF-" + b"x" * 5))
    with pytest.raises(HTTPException) as error_info:
        validate_pdf_stream("a.pdf", BytesIO(b"%PDF-" + b"x" * 6))

    assert_http_error(error_info, 413, "PAYLOAD_TOO_LARGE")


def test_extract_document_maps_invalid_pdf():
    with pytest.raises(HTTPException) as error_info:
        extract_document("a.pdf", BytesIO(b"%PDF-1.4\nnot a document"))

    assert_http_error(error_info, 400, "INVALID_OR_ENCRYPTED_PDF")


def test_extract_document_maps_page_limit(make_pdf, monkeypatch):
    monkeypatch.setattr(document_service, "MAX_PDF_PAGES", 2)

    with pytest.raises(HTTPException) as error_info:
        extract_document("a.pdf", BytesIO(make_pdf(["x"] * 3)))

    assert_http_error(error_info, 422, "PDF_TOO_MANY_PAGES")


# ── compare_document ─────────────────────────────────────

def test_compare_document_checks_both_files_before_extracting(make_pdf, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.services.comparison_service.run_in_worker",
        lambda *args, **kwargs: calls.append(args),
    )

    with pytest.raises(HTTPException) as error_info:
        compare_document("old.pdf", BytesIO(make_pdf(["x"])), "new.pdf", BytesIO(b"hello"))

    assert_http_error(error_info, 400, "INVALID_OR_ENCRYPTED_PDF")
    assert "new.pdf" in error_info.value.detail["detail"]
    assert calls == []


def test_compare_document_rejects_long_extracted_text(make_pdf, monkeypatch):
    monkeypatch.setattr("app.services.comparison_service.MAX_TEXT_CHARS", 10)

    with pytest.raises(HTTPException) as error_info:
        compare_document(
            "old.pdf", BytesIO(make_pdf(["short"])),
            "new.pdf", BytesIO(make_pdf(["a much longer text"])),
        )

    assert_http_error(error_info, 422, "TEXT_TOO_LONG")


def test_compare_document_blank_pages_need_review(make_pdf):
    result = compare_document(
        "old.pdf", BytesIO(make_pdf([""])),
        "new.pdf", BytesIO(make_pdf([""])),
    )

    assert result["changes"] == []
    assert result["needs_review"] is True


def test_compare_document_rejects_long_old_text_before_parsing_new(make_pdf, monkeypatch):
    # Fail-fast: old quá dài thì không parse new (new có thể hỏng hoặc gây treo).
    monkeypatch.setattr("app.services.comparison_service.MAX_TEXT_CHARS", 10)

    with pytest.raises(HTTPException) as error_info:
        compare_document(
            "old.pdf", BytesIO(make_pdf(["a much longer text"])),
            "new.pdf", BytesIO(b"%PDF-1.4\nnot a document"),
        )

    assert_http_error(error_info, 422, "TEXT_TOO_LONG")
    assert "old.pdf" in error_info.value.detail["detail"]


def test_config_values_follow_plan_v2():
    assert config.MAX_UPLOAD_FILE_BYTES == 15 * 1024 * 1024
    assert config.MAX_PDF_PAGES == 100
    assert config.MAX_TEXT_CHARS == 500_000
    assert config.MAX_REQUEST_BODY_BYTES == 2 * config.MAX_UPLOAD_FILE_BYTES + 1024 * 1024
    assert config.COMPARISON_TIMEOUT_SECONDS == 30
    assert config.MAX_ACTIVE_WORKERS == 2
