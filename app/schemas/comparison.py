from pydantic import BaseModel, Field, field_validator

from app.core.config import MAX_TEXT_CHARS
from app.schemas.document import DocumentExtractionResponse

class TextComparisonRequest(BaseModel):
    old_text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    new_text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)

    @field_validator("old_text", "new_text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        # strip() dùng cùng định nghĩa khoảng trắng với tokenizer r"\S+".
        if not value.strip():
            raise ValueError("Văn bản không được chỉ chứa khoảng trắng")
        return value

class TextSpan(BaseModel):
    start: int
    end: int

class PageLocation(BaseModel):
    page_number: int
    start: int
    end: int


class ChangeItem(BaseModel):
    type: str
    old_text: str
    new_text: str
    old_span: TextSpan | None
    new_span: TextSpan | None
    old_locations: list[PageLocation] = []
    new_locations: list[PageLocation] = []

class TextComparisonResponse(BaseModel):
    is_identical: bool
    is_token_identical: bool
    old_length: int
    new_length: int
    changes: list[ChangeItem]

class PDFComparisonResponse(BaseModel):
    old_document: DocumentExtractionResponse
    new_document: DocumentExtractionResponse
    changes: list[ChangeItem]
    needs_review: bool
