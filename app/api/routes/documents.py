from fastapi import APIRouter,UploadFile
from app.schemas.document import (DocumentExtractionResponse)
from app.services.document_service import extract_document

router = APIRouter()

@router.post("/extract", response_model=DocumentExtractionResponse)
def extract_document_endpoint(file: UploadFile):
    return extract_document(
        file.filename or "document.pdf",
        file.file,
    )
    