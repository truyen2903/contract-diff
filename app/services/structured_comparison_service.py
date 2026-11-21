from app.core.jobs import compare_structured_pdf_files, compare_structured_texts
from app.core.worker import run_in_worker
from app.engines.alignment_budget import AlignmentBudgetError, AlignmentResultTooLargeError, StructureTooLargeError
from app.schemas.alignment import StructuredComparisonResponse
from app.schemas.comparison import TextComparisonRequest
from app.services.document_service import DOCUMENT_ERRORS, document_error, http_error, validate_pdf_stream
from pydantic import ValidationError


ALIGNMENT_ERRORS = (AlignmentBudgetError, AlignmentResultTooLargeError, StructureTooLargeError)


def run_structured(job, *args, names, **kwargs):
    try:
        result = run_in_worker(job, *args, expected_errors=DOCUMENT_ERRORS + ALIGNMENT_ERRORS, **kwargs)
    except DOCUMENT_ERRORS as error:
        raise document_error(names[error.side], error) from error
    except ALIGNMENT_ERRORS as error:
        side = getattr(error, "side", None)
        detail = f"{names[side]}: {error}" if side in names else str(error)
        raise http_error(422, error.code, detail) from error
    try:
        StructuredComparisonResponse.model_validate(result)
    except ValidationError as error:
        raise http_error(500, "PROCESSING_FAILED", "Kết quả structured không hợp lệ") from error
    return result


def compare_structured_text(old_text: str, new_text: str):
    request = TextComparisonRequest(old_text=old_text, new_text=new_text)
    return run_structured(compare_structured_texts, request.old_text, request.new_text,
                          names={"old": "old", "new": "new"})


def compare_structured_document(old_filename, old_file_stream, new_filename, new_file_stream):
    validate_pdf_stream(old_filename, old_file_stream)
    validate_pdf_stream(new_filename, new_file_stream)
    return run_structured(compare_structured_pdf_files, files=[old_file_stream, new_file_stream],
                          names={"old": old_filename, "new": new_filename})
