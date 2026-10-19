from pydantic import BaseModel, Field

class TextComparisonRequest(BaseModel):
    old_text:str  = Field(min_length=1)
    new_text:str = Field(min_length=1)
    

class ChangeItem(BaseModel):
    type: str
    old_text: str
    new_text: str
    old_span:str
    new_span:str


class TextComparisonResponse(BaseModel):
    is_identical: bool  
    old_length: int
    new_length: int
    changes: list[ChangeItem]