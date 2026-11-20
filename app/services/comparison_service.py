from app.core.config import MAX_PDF_PAGES, MAX_TEXT_CHARS
from app.core.jobs import compare_pdf_files
from app.core.worker import run_in_worker
from app.engines.text_diff import diff_words
from app.services.document_service import DOCUMENT_ERRORS, document_error, validate_pdf_stream

def compare_text(old_text: str, new_text: str):
    # Hai chuỗi giống hệt thì không có thay đổi: không cần tạo worker.
    changes = [] if old_text == new_text else run_in_worker(diff_words, old_text, new_text)

    return {
        "is_identical": old_text == new_text,
        "is_token_identical": len(changes) == 0,
        "old_length": len(old_text),
        "new_length": len(new_text),
        "changes": changes,
    }

def compare_document(old_filename, old_file_stream,new_filename, new_file_stream):
    # Kiểm tra rẻ cả hai tệp trước khi giao cho worker parse.
    validate_pdf_stream(old_filename, old_file_stream)
    validate_pdf_stream(new_filename, new_file_stream)

    try:
        old_pages, new_pages, changes = run_in_worker(
            compare_pdf_files, MAX_PDF_PAGES, MAX_TEXT_CHARS,
            files=[old_file_stream, new_file_stream],
            expected_errors=DOCUMENT_ERRORS,
        )
    except DOCUMENT_ERRORS as error:
        # Worker ghi side ("old"/"new") vào lỗi để biết tệp nào hỏng.
        filename = old_filename if error.side == "old" else new_filename
        raise document_error(filename, error) from error

    old_document = {"filename": old_filename, "page_count": len(old_pages), "pages": old_pages}
    new_document = {"filename": new_filename, "page_count": len(new_pages), "pages": new_pages}
    
    needs_review = any(
    page["warnings"] for page in old_document["pages"] + new_document["pages"])
        
    return {
        "old_document":old_document,
        "new_document":new_document,
        "changes":changes,
        "needs_review": needs_review,
    }