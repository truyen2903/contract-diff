from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    PREAMBLE = "PREAMBLE"
    ARTICLE = "ARTICLE"
    CLAUSE = "CLAUSE"
    PARAGRAPH = "PARAGRAPH"
    TABLE = "TABLE"  # Chưa sinh trong Phase B1.
    SIGNATURE = "SIGNATURE"


class BoundingBox(BaseModel):
    page: int = Field(ge=1)
    x0: float
    top: float
    x1: float
    bottom: float


class SourceSpan(BaseModel):
    page_number: int = Field(ge=1)
    raw_char_start: int = Field(ge=0)   # Trong text của trang nguồn.
    raw_char_end: int = Field(ge=0)
    clean_char_start: int = Field(ge=0)  # Trong normalized_text của tài liệu.
    clean_char_end: int = Field(ge=0)
    bbox: BoundingBox | None = None
    source_type: Literal["PLAIN_TEXT", "PDF_DIGITAL"]


class StructuralNode(BaseModel):
    node_id: str
    node_type: NodeType
    parent_id: str | None = None
    children: list[str] = []
    section_context: str | None = None
    number_label: str | None = None
    title: str | None = None
    own_text: str
    subtree_text: str
    page_numbers: list[int] = []
    bboxes: list[BoundingBox] = []
    source_spans: list[SourceSpan] = []
    warnings: list[str] = []


class SourceLine(BaseModel):
    page_number: int = Field(ge=1)
    line_index: int = Field(ge=0)
    text: str
    raw_start: int = Field(ge=0)
    raw_end: int = Field(ge=0)
    raw_offsets_exact: bool = False
    clean_start: int = Field(ge=0)
    clean_end: int = Field(ge=0)
    bbox: BoundingBox | None = None
    masked: bool
    mask_reason: str | None = None


class PageWarnings(BaseModel):
    page_number: int = Field(ge=1)
    warnings: list[str]


class DocumentStructure(BaseModel):
    source_type: Literal["PLAIN_TEXT", "PDF_DIGITAL"]
    page_count: int = Field(ge=0)
    normalized_text: str
    lines: list[SourceLine]
    page_warnings: list[PageWarnings]
    nodes: list[StructuralNode]
    warnings: list[str]
    needs_review: bool
