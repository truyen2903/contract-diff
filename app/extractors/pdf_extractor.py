from itertools import islice

import pdfplumber
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfplumber.utils.exceptions import PdfminerException

INVALID_PDF_MESSAGE = "Tệp PDF hỏng hoặc cần mật khẩu"
# Lỗi phía server, không phải lỗi dữ liệu PDF: luôn để lan ra (HTTP 500).
SERVER_ERRORS = (OSError, MemoryError)


class InvalidPDFError(ValueError):
    pass


class PDFPageLimitError(ValueError):
    pass


def raise_invalid_pdf(error):
    # pdfplumber bọc mọi lỗi trong PdfminerException; xét lỗi gốc bên trong.
    cause = error
    if isinstance(error, PdfminerException) and error.args:
        cause = error.args[0]
    if isinstance(cause, SERVER_ERRORS):
        raise error
    raise InvalidPDFError(INVALID_PDF_MESSAGE) from error


def count_pdf_pages(file_stream, max_pages: int) -> int:
    # Đếm bằng pdfminer trước khi mở pdfplumber: dừng ở trang max_pages + 1,
    # vì PDF.close() của pdfplumber dựng lại mọi trang.
    try:
        document = PDFDocument(PDFParser(file_stream), password="")
        return sum(1 for _ in islice(PDFPage.create_pages(document), max_pages + 1))
    except Exception as error:
        # Khối try chỉ gọi thư viện trên dữ liệu không tin cậy.
        raise_invalid_pdf(error)


def read_page_texts(file_stream) -> list[str]:
    try:
        with pdfplumber.open(file_stream) as pdf:
            return [page.extract_text() or "" for page in pdf.pages]
    except Exception as error:
        raise_invalid_pdf(error)


def extract_pdf(file_stream, max_pages: int) -> list[dict]:
    file_stream.seek(0)
    page_count = count_pdf_pages(file_stream, max_pages)
    if page_count == 0:
        raise InvalidPDFError("Tệp PDF không có trang nào")
    if page_count > max_pages:
        raise PDFPageLimitError(f"Tệp PDF vượt quá {max_pages} trang")

    file_stream.seek(0)
    pages = []
    for page_number, text in enumerate(read_page_texts(file_stream), start=1):
        warnings = []
        if "\x00" in text:
            warnings.append("NULL_CHARACTER")
        if not text.replace("\x00", "").strip():
            warnings.append("EMPTY_TEXT")
        pages.append({
            "page_number": page_number,
            "text": text,
            "warnings": warnings,
        })
    return pages
