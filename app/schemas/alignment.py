"""Validation of side-local references, complete node coverage and source offsets."""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.engines.clause_aligner import validate_config
from app.engines.similarity import body_start
from app.extractors.layout_cleaner import REVIEW_PAGE_WARNINGS


Side = Literal["old", "new"]
Kind = Literal["PREAMBLE", "PARAGRAPH", "ARTICLE", "CLAUSE", "SIGNATURE", "TABLE"]
Score = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Offset = Annotated[int, Field(ge=0)]
NodeID = Annotated[str, Field(min_length=1)]
Stage = Literal["EXACT_ANCHOR", "STAGE1_ARTICLE", "STAGE1_INTRA_CLAUSE",
                "STAGE2_ORPHAN_CLAUSE", "STAGE1_BLOCK", "UNMATCHED"]
Category = Literal["ADDED", "DELETED", "UNCHANGED", "MODIFIED", "MOVED", "MOVED_AND_MODIFIED", "RENUMBERED"]
EntityType = Literal["MONEY", "DATE", "DURATION", "PERCENTAGE", "MODALITY", "CROSS_REF"]
EvidenceScope = Literal["EXPLICIT", "INHERITED", "UNRESOLVED"]
CalendarType = Literal["CALENDAR", "WORKING", "UNSPECIFIED"]
SemanticSignal = Literal["MONEY_CHANGE", "DATE_DURATION_CHANGE", "PERCENTAGE_CHANGE",
                         "MODALITY_SIGNAL_CHANGE", "CROSS_REF_CHANGE", "TEXT_EDIT",
                         "FORMATTING_ONLY", "INTERNAL_CROSS_REFERENCE_RISK"]
ReviewPriority = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class CompactModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AlignmentConfig(CompactModel):
    tau_min: Score
    tau_lex_floor: Score
    tau_orphan: Score
    tau_high: Score
    delta_margin: Score
    edge_penalty_alpha: Score
    one_sided_title: Literal["omit", "half", "zero"]
    move_convention: Literal["v2-4.3-zero-based-v1"]

    @model_validator(mode="after")
    def check_thresholds(self):
        validate_config(self.model_dump())
        return self


class SourceSegment(CompactModel):
    page: int = Field(ge=1)
    own_start: Offset
    own_end: Offset
    clean_start: Offset
    clean_end: Offset
    raw_start: Offset
    raw_end: Offset
    raw_exact: bool


class CompactNode(CompactModel):
    node_id: NodeID
    node_type: Kind
    parent_id: NodeID | None
    own_text: str
    section_context: str | None
    number_label: str | None
    title: str | None
    warnings: list[str]
    body_offset: Offset
    raw_offsets_exact: bool
    source_segments: list[SourceSegment]

    @model_validator(mode="after")
    def check_mapping(self):
        if self.body_offset != body_start(self.own_text, self.number_label)[0]:
            raise ValueError("invalid body offset")
        end = 0
        previous = None
        for s in self.source_segments:
            size = s.own_end - s.own_start
            if (size <= 0 or s.clean_end - s.clean_start != size or s.raw_end <= s.raw_start
                    or (s.raw_exact and s.raw_end - s.raw_start != size)):
                raise ValueError("inconsistent segment length")
            if previous:
                if (s.own_start != end + 1 or self.own_text[end:end + 1] != "\n"
                        or s.clean_start <= previous.clean_end or s.page < previous.page
                        or (s.page == previous.page and s.raw_start <= previous.raw_end)):
                    raise ValueError("source segments out of order")
            elif s.own_start != 0:
                raise ValueError("unmapped prefix")
            end, previous = s.own_end, s
        if end != len(self.own_text) or self.raw_offsets_exact != all(s.raw_exact for s in self.source_segments):
            raise ValueError("incomplete source map")
        return self


class PageWarnings(CompactModel):
    page_number: int = Field(ge=1)
    warnings: list[str]


class CompactDocument(CompactModel):
    side: Side
    source_type: Literal["PLAIN_TEXT", "PDF_DIGITAL"]
    page_count: Offset
    page_warnings: list[PageWarnings]
    warnings: list[str]
    needs_review: bool
    nodes: list[CompactNode]

    @model_validator(mode="after")
    def check_tree(self):
        nodes = {n.node_id: n for n in self.nodes}
        review_pages = any(w in REVIEW_PAGE_WARNINGS for p in self.page_warnings for w in p.warnings)
        if self.needs_review != bool(self.warnings or any(n.warnings for n in self.nodes) or review_pages):
            raise ValueError("inconsistent document review status")
        if len(nodes) != len(self.nodes):
            raise ValueError("duplicate document node")
        if len(self.page_warnings) != self.page_count or any(
                p.page_number != i for i, p in enumerate(self.page_warnings, 1)):
            raise ValueError("incomplete page warnings")
        for node in self.nodes:
            if node.node_type == "CLAUSE":
                parent = nodes.get(node.parent_id)
                if parent is None or parent.node_type != "ARTICLE":
                    raise ValueError("invalid clause parent")
            elif node.parent_id is not None:
                raise ValueError("invalid root parent")
            if any(s.page > self.page_count for s in node.source_segments):
                raise ValueError("unknown page")
        segments = [s for node in self.nodes for s in node.source_segments]
        last_clean, page_ends = -1, {}
        for segment in sorted(segments, key=lambda s: s.clean_start):
            if segment.clean_start < last_clean or segment.raw_start < page_ends.get(segment.page, 0):
                raise ValueError("overlapping source ownership")
            last_clean = segment.clean_end
            page_ends[segment.page] = segment.raw_end
        return self


class Candidate(CompactModel):
    candidate_side: Side
    node_id: NodeID
    score: Score


class Span(CompactModel):
    start: Offset
    end: Offset


class WordChange(CompactModel):
    type: Literal["insert", "delete", "replace"]
    old_span: Span | None
    new_span: Span | None


class EntityEvidence(CompactModel):
    page: int = Field(ge=1)
    clean_start: Offset
    clean_end: Offset
    raw_start: Offset
    raw_end: Offset
    raw_exact: bool
    source_node_id: NodeID | None = None


class NormalizedEntityValue(CompactModel):
    entity_id: str = Field(min_length=1)
    signal_type: EntityType
    raw_text: str
    char_start: Offset
    char_end: Offset
    normalized_value: str | None = None
    money_amount: str | None = Field(default=None, pattern=r"^\d+(?:\.\d+)?$")
    money_currency: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9]{1,7}$")
    money_numeric_raw: str | None = None
    money_spelled_raw: str | None = None
    duration_value: str | None = Field(default=None, pattern=r"^\d+(?:\.\d+)?$")
    duration_unit: Literal["HOUR", "DAY", "WEEK", "MONTH", "YEAR"] | None = None
    calendar_type: CalendarType | None = None
    date_iso: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    percentage_rate: str | None = Field(default=None, pattern=r"^\d+(?:\.\d+)?$")
    percentage_period: Literal["DAY", "MONTH", "YEAR", "NONE"] | None = None
    percentage_base: str | None = None
    percentage_cap: str | None = None
    percentage_trigger: str | None = None
    modality_group: Literal["OBLIGATION", "PERMISSION", "PROHIBITION_EXEMPTION"] | None = None
    cross_ref_target: str | None = None
    is_ambiguous: bool = False
    ambiguity_reason: str | None = None
    evidence_scope: EvidenceScope = "EXPLICIT"
    context_source_node_id: NodeID | None = None
    source_evidence: list[EntityEvidence] = Field(default_factory=list)


class EntityDelta(CompactModel):
    signal_type: SemanticSignal
    old_entity: NormalizedEntityValue | None = None
    new_entity: NormalizedEntityValue | None = None
    is_value_changed: bool
    summary: str
    pairing_status: Literal["PAIRED", "ADDED", "DELETED", "AMBIGUOUS"]


class AlignedPair(CompactModel):
    old_node_id: NodeID | None
    new_node_id: NodeID | None
    node_type: Kind
    category: Category
    alignment_stage: Stage
    parent_status: Literal["SAME", "CHANGED", "UNKNOWN"] | None
    parent_changed: bool | None
    similarity_score: Score
    alignment_confidence: Score
    second_best_gap: Score
    alternative_candidates: list[Candidate] = Field(max_length=2)
    warnings: list[str]
    needs_review: bool
    word_changes: list[WordChange]
    old_entities: list[NormalizedEntityValue] = Field(default_factory=list)
    new_entities: list[NormalizedEntityValue] = Field(default_factory=list)
    entity_deltas: list[EntityDelta] = Field(default_factory=list)
    semantic_signals: list[SemanticSignal] = Field(default_factory=list)
    review_priority: ReviewPriority = "LOW"
    review_reasons: list[str] = Field(default_factory=list)


TOKEN = re.compile(r"\S+")


def validate_edits(old, new, changes):
    """Replay unchanged gaps in lockstep. A one-sided opcode has an implicit opposite cursor."""
    nodes = (old, new)
    bodies = [n.own_text[n.body_offset:] if n else "" for n in nodes]
    identical = bodies[0].split() == bodies[1].split()
    if identical != (not changes):
        raise ValueError("word changes inconsistent with body tokens")
    if not changes:
        return
    streams = [TOKEN.finditer(n.own_text, n.body_offset) if n else iter(()) for n in nodes]
    heads = [next(it, None) for it in streams]
    for change in changes:
        spans = (change.old_span, change.new_span)
        if (spans[0] is None) != (change.type == "insert") or (spans[1] is None) != (change.type == "delete"):
            raise ValueError("invalid opcode spans")
        while any(s and h and h.start() < s.start for s, h in zip(spans, heads)):
            if not all(heads) or heads[0].group() != heads[1].group():
                raise ValueError("mismatched unchanged opcode prefix")
            heads = [next(it, None) for it in streams]
        for i, span in enumerate(spans):
            if span is None:
                continue
            head = heads[i]
            if not head or head.start() != span.start:
                raise ValueError("opcode does not start at current token")
            while head and head.end() < span.end:
                head = next(streams[i], None)
            if not head or head.end() != span.end:
                raise ValueError("opcode does not end on a complete token")
            heads[i] = next(streams[i], None)
    while all(heads) and heads[0].group() == heads[1].group():
        heads = [next(it, None) for it in streams]
    if any(heads):
        raise ValueError("word changes do not cover the suffix")


def validate_pair(row, nodes, parents, paired_parents):
    ids = {"old": row.old_node_id, "new": row.new_node_id}
    old, new = (nodes[side].get(key) for side, key in ids.items())
    paired = old is not None and new is not None
    if not paired and any((row.similarity_score, row.alignment_confidence, row.second_best_gap)):
        raise ValueError("unmatched node with match scores")
    if row.alignment_stage == "EXACT_ANCHOR" and (row.similarity_score != 1 or row.alignment_confidence != 1):
        raise ValueError("invalid anchor score")
    if row.node_type not in ("ARTICLE", "CLAUSE") and row.category in ("MOVED", "MOVED_AND_MODIFIED"):
        raise ValueError("block outside move convention")
    if ((old is None) != (row.category == "ADDED") or (new is None) != (row.category == "DELETED")
            or paired == (row.alignment_stage == "UNMATCHED")):
        raise ValueError("category or stage inconsistent with endpoints")
    status = None
    if paired and row.node_type == "CLAUSE":
        if parents.get(old.parent_id) == new.parent_id:
            status = "SAME"
        elif old.parent_id in parents or new.parent_id in paired_parents:
            status = "CHANGED"
        else:
            status = "UNKNOWN"
    if status != row.parent_status or row.parent_changed != {"CHANGED": True, "SAME": False}.get(status):
        raise ValueError("incorrect parent status")
    moving = row.category in ("MOVED", "MOVED_AND_MODIFIED")
    if (status == "CHANGED" and (not moving or "CROSS_ARTICLE_CLAUSE_MOVE" not in row.warnings)
            or status == "UNKNOWN" and (moving or "PARENT_ALIGNMENT_UNKNOWN" not in row.warnings)):
        raise ValueError("invalid parent classification")
    if row.needs_review != bool(row.warnings):
        raise ValueError("inconsistent review status")
    if paired:
        stages = {"ARTICLE": ("STAGE1_ARTICLE",), "CLAUSE": ("STAGE1_INTRA_CLAUSE", "STAGE2_ORPHAN_CLAUSE")}
        if row.alignment_stage not in ("EXACT_ANCHOR", *stages.get(row.node_type, ("STAGE1_BLOCK",))):
            raise ValueError("stage does not match node type")
        if row.alignment_stage == "STAGE1_INTRA_CLAUSE" and status != "SAME":
            raise ValueError("local match outside parent")
    seen = set()
    for c in row.alternative_candidates:
        side = c.candidate_side
        other = nodes[side].get(c.node_id)
        ref = side, c.node_id
        if (ref in seen or not other or other.node_type != row.node_type or c.node_id == ids[side]
                or (not paired and ids[side] is not None)):
            raise ValueError("invalid alternative candidate")
        seen.add(ref)
    if paired and bool(row.word_changes) != (row.category in ("MODIFIED", "MOVED_AND_MODIFIED")):
        raise ValueError("word changes inconsistent with category")
    if paired and row.category in ("UNCHANGED", "RENUMBERED"):
        if (old.number_label == new.number_label) != (row.category == "UNCHANGED"):
            raise ValueError("category inconsistent with numbering")
    for side, node, entities in (("old", old, row.old_entities), ("new", new, row.new_entities)):
        if node is None and entities:
            raise ValueError(f"{side} entities on an unmatched row")
        if node is None:
            continue
        for entity in entities:
            if entity.evidence_scope != "INHERITED":
                if not (entity.char_start < entity.char_end <= len(node.own_text)):
                    raise ValueError("entity span outside own_text")
                if entity.raw_text != node.own_text[entity.char_start:entity.char_end]:
                    raise ValueError("entity raw text does not match own_text")
                if not entity.source_evidence:
                    raise ValueError("direct entity lacks source evidence")
                for evidence in entity.source_evidence:
                    if evidence.clean_start >= evidence.clean_end or evidence.raw_start > evidence.raw_end:
                        raise ValueError("invalid entity source evidence")
                    if not any(segment.page == evidence.page
                               and segment.clean_start <= evidence.clean_start
                               and evidence.clean_end <= segment.clean_end
                               for segment in node.source_segments):
                        raise ValueError("entity source evidence outside source segments")
            elif entity.char_start != 0 or entity.char_end != 0:
                raise ValueError("contextual entity must not claim a child span")
            if entity.evidence_scope == "INHERITED":
                if not entity.context_source_node_id or entity.context_source_node_id != node.parent_id:
                    raise ValueError("inherited entity lacks owning parent context")
        if any(a.entity_id == b.entity_id for i, a in enumerate(entities) for b in entities[i + 1:]):
            raise ValueError("duplicate entity identifier")
    if row.review_priority == "CRITICAL" and not row.needs_review:
        raise ValueError("critical priority requires review")
    validate_edits(old, new, row.word_changes)


class StructuredComparisonResponse(CompactModel):
    old_document: CompactDocument
    new_document: CompactDocument
    alignments: list[AlignedPair]
    config: AlignmentConfig
    warnings: list[str]
    needs_review: bool
    b3_schema_version: str = "b3-v1"
    entity_rules_version: str = "b3-rules-v1"
    priority_rules_version: str = "b3-priority-v1"

    @model_validator(mode="after")
    def check_references(self):
        nodes, seen = {}, {"old": set(), "new": set()}
        for side, doc in (("old", self.old_document), ("new", self.new_document)):
            if doc.side != side:
                raise ValueError("incorrect document side")
            nodes[side] = {n.node_id: n for n in doc.nodes}
        parents = {r.old_node_id: r.new_node_id for r in self.alignments
                   if r.node_type == "ARTICLE" and r.old_node_id is not None and r.new_node_id is not None}
        paired = set(parents.values())
        for row in self.alignments:
            for side, key in (("old", row.old_node_id), ("new", row.new_node_id)):
                if key is not None:
                    if key in seen[side] or key not in nodes[side] or nodes[side][key].node_type != row.node_type:
                        raise ValueError("invalid or reused node reference")
                    seen[side].add(key)
            validate_pair(row, nodes, parents, paired)
        if any(seen[s] != nodes[s].keys() for s in nodes):
            raise ValueError("missing alignment record")
        expected = set(self.old_document.warnings + self.new_document.warnings)
        expected.update(w for row in self.alignments for w in row.warnings)
        if self.warnings != sorted(expected) or self.needs_review != bool(
                expected or self.old_document.needs_review or self.new_document.needs_review):
            raise ValueError("inconsistent result warnings")
        return self
