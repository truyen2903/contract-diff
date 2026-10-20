from pydantic import BaseModel

class DocumentPage(BaseModel):
    page_number:int
    text:str
    warnings: list[str]
    
class DocumentExtractionResponse(BaseModel):
    filename:str
    page_count:int
    pages:list[DocumentPage]