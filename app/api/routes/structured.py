"""Public B3 structured comparison operations for the local research UI."""

import re
from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from app.schemas.alignment import StructuredComparisonResponse
from app.schemas.comparison import StructuredTextRequest
from app.services.structured_comparison_service import compare_structured_document, compare_structured_text


router = APIRouter()


def safe_filename(filename: str | None, fallback: str) -> str:
    """Keep error details bounded and prevent client filenames becoming paths."""
    name = Path(filename or fallback).name
    name = re.sub(r"[\x00-\x1f\x7f]", "_", name).strip() or fallback
    return name[:128]


@router.post("/text", response_model=StructuredComparisonResponse,
             summary="Compare two contract texts with structure and semantic signals")
def structured_text_endpoint(payload: StructuredTextRequest):
    return compare_structured_text(payload.old_text, payload.new_text)


@router.post("/pdf", response_model=StructuredComparisonResponse,
             summary="Compare two digital contract PDFs with structure and semantic signals")
def structured_pdf_endpoint(
    old_file: UploadFile = File(..., description="Old contract PDF"),
    new_file: UploadFile = File(..., description="New contract PDF"),
):
    return compare_structured_document(
        safe_filename(old_file.filename, "old_document.pdf"), old_file.file,
        safe_filename(new_file.filename, "new_document.pdf"), new_file.file,
    )
