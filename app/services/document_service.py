import os

from fastapi import HTTPException

from app.core.config import MAX_PDF_PAGES, MAX_UPLOAD_FILE_BYTES
from app.core.jobs import TextTooLongError, extract_pdf_file
from app.core.worker import run_in_worker
from app.extractors.pdf_extractor import InvalidPDFError, PDFPageLimitError

# Lỗi do input mà worker trả về; lỗi khác không bị dán nhãn thành lỗi của tệp.
DOCUMENT_ERRORS = (InvalidPDFError, PDFPageLimitError, TextTooLongError)

def http_error(status_code, error_code, detail):
    return HTTPException(
        status_code=status_code,
        detail={"error_code": error_code, "detail": detail},
    )

def validate_pdf_stream(filename, file_stream):
    # Kiểm tra rẻ trước khi parse: kích thước bằng seek, không đọc toàn tệp.
    size = file_stream.seek(0, os.SEEK_END)
    file_stream.seek(0)
    if size > MAX_UPLOAD_FILE_BYTES:
        raise http_error(413, "PAYLOAD_TOO_LARGE", f"{filename}: tệp vượt quá {MAX_UPLOAD_FILE_BYTES} byte")
    header = file_stream.read(5)
    file_stream.seek(0)
    if header != b"%PDF-":
        raise http_error(400, "INVALID_OR_ENCRYPTED_PDF", f"{filename}: không phải tệp PDF")

def document_error(filename, error):
    if isinstance(error, InvalidPDFError):
        return http_error(400, "INVALID_OR_ENCRYPTED_PDF", f"{filename}: {error}")
    if isinstance(error, PDFPageLimitError):
        return http_error(422, "PDF_TOO_MANY_PAGES", f"{filename}: {error}")
    return http_error(422, "TEXT_TOO_LONG", f"{filename}: {error}")

def extract_document(filename, file_stream):
    validate_pdf_stream(filename, file_stream)
    try:
        pages= run_in_worker(extract_pdf_file, MAX_PDF_PAGES, files=[file_stream], expected_errors=DOCUMENT_ERRORS)
    except DOCUMENT_ERRORS as error:
        raise document_error(filename, error) from error
    page_count = len(pages)
    return {
    "filename":filename,
    "page_count":page_count,
    "pages":pages   
            }

