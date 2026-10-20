from pydantic import BaseModel, Field
from app.schemas.document import DocumentExtractionResponse

class TextComparisonRequest(BaseModel):
    old_text:str  = Field(min_length=1)
    new_text:str = Field(min_length=1)
    
class TextSpan(BaseModel):
    start: int
    end: int

class ChangeItem(BaseModel):
    type: str
    old_text: str
    new_text: str
    old_span: TextSpan | None
    new_span: TextSpan | None

class TextComparisonResponse(BaseModel):
    is_identical: bool  
    old_length: int
    new_length: int
    changes: list[ChangeItem]

class PDFComparisonResponse(BaseModel):
    old_document: DocumentExtractionResponse
    new_document: DocumentExtractionResponse
    changes: list[ChangeItem]
    needs_review: bool