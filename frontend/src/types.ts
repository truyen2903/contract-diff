export type NodeType = 'PREAMBLE' | 'PARAGRAPH' | 'ARTICLE' | 'CLAUSE' | 'SIGNATURE' | 'TABLE'
export type ChangeCategory = 'ADDED' | 'DELETED' | 'UNCHANGED' | 'MODIFIED' | 'MOVED' | 'MOVED_AND_MODIFIED' | 'RENUMBERED'
export type ReviewPriority = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'

export interface SourceSegment {
  page: number
  own_start: number
  own_end: number
  clean_start: number
  clean_end: number
  raw_start: number
  raw_end: number
  raw_exact: boolean
}

export interface CompactNode {
  node_id: string
  node_type: NodeType
  parent_id: string | null
  own_text: string
  section_context: string | null
  number_label: string | null
  title: string | null
  warnings: string[]
  body_offset: number
  raw_offsets_exact: boolean
  source_segments: SourceSegment[]
}

export interface CompactDocument {
  side: 'old' | 'new'
  source_type: 'PLAIN_TEXT' | 'PDF_DIGITAL'
  page_count: number
  page_warnings: { page_number: number; warnings: string[] }[]
  warnings: string[]
  needs_review: boolean
  nodes: CompactNode[]
}

export interface Span { start: number; end: number }
export interface WordChange { type: 'insert' | 'delete' | 'replace'; old_span: Span | null; new_span: Span | null }

export interface EntityEvidence {
  page: number
  clean_start: number
  clean_end: number
  raw_start: number
  raw_end: number
  raw_exact: boolean
  source_node_id: string | null
}

export interface Entity {
  entity_id: string
  signal_type: 'MONEY' | 'DATE' | 'DURATION' | 'PERCENTAGE' | 'MODALITY' | 'CROSS_REF'
  raw_text: string
  char_start: number
  char_end: number
  normalized_value?: string | null
  money_amount?: string | null
  money_currency?: string | null
  duration_value?: string | null
  duration_unit?: string | null
  calendar_type?: 'CALENDAR' | 'WORKING' | 'UNSPECIFIED' | null
  date_iso?: string | null
  percentage_rate?: string | null
  percentage_period?: string | null
  modality_group?: string | null
  cross_ref_target?: string | null
  is_ambiguous: boolean
  ambiguity_reason?: string | null
  evidence_scope: 'EXPLICIT' | 'INHERITED' | 'UNRESOLVED'
  source_evidence: EntityEvidence[]
}

export interface EntityDelta {
  signal_type: 'MONEY_CHANGE' | 'DATE_DURATION_CHANGE' | 'PERCENTAGE_CHANGE' | 'MODALITY_SIGNAL_CHANGE' | 'CROSS_REF_CHANGE' | 'TEXT_EDIT' | 'FORMATTING_ONLY' | 'INTERNAL_CROSS_REFERENCE_RISK'
  old_entity: Entity | null
  new_entity: Entity | null
  is_value_changed: boolean
  summary: string
  pairing_status: 'PAIRED' | 'ADDED' | 'DELETED' | 'AMBIGUOUS'
}

export interface Candidate { candidate_side: 'old' | 'new'; node_id: string; score: number }

export interface AlignmentRow {
  old_node_id: string | null
  new_node_id: string | null
  node_type: NodeType
  category: ChangeCategory
  alignment_stage: string
  parent_status: 'SAME' | 'CHANGED' | 'UNKNOWN' | null
  parent_changed: boolean | null
  similarity_score: number
  alignment_confidence: number
  second_best_gap: number
  alternative_candidates: Candidate[]
  warnings: string[]
  needs_review: boolean
  word_changes: WordChange[]
  old_entities: Entity[]
  new_entities: Entity[]
  entity_deltas: EntityDelta[]
  semantic_signals: EntityDelta['signal_type'][]
  review_priority: ReviewPriority
  review_reasons: string[]
}

export interface StructuredResult {
  old_document: CompactDocument
  new_document: CompactDocument
  alignments: AlignmentRow[]
  config: Record<string, unknown>
  warnings: string[]
  needs_review: boolean
  b3_schema_version: string
  entity_rules_version: string
  priority_rules_version: string
}
