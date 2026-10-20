from fastapi import APIRouter,UploadFile

from app.schemas.comparison import (TextComparisonRequest,TextComparisonResponse,PDFComparisonResponse)

from app.services.comparison_service import compare_text,compare_document

router = APIRouter()

@router.post("/text",response_model=TextComparisonResponse)
def compare_text_endpoint(payload: TextComparisonRequest):
    result  = compare_text(payload.old_text,payload.new_text)
    return result
@router.post("/pdf",response_model=PDFComparisonResponse)
def compare_document_endpoint(old_file: UploadFile,new_file: UploadFile):
    return compare_document(
        old_file.filename,
        old_file.file,
        new_file.filename,
        new_file.file
           )