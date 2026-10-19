from fastapi import APIRouter

from app.schemas.comparison import (TextComparisonRequest,TextComparisonResponse)

from app.services.comparison_service import compare_text

router = APIRouter()

@router.post("/text",response_model=TextComparisonResponse)
def compare_text_endpoint(payload: TextComparisonRequest):
    result  = compare_text(payload.old_text,payload.new_text)
    return result
