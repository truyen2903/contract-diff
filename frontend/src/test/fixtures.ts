import type { StructuredResult } from '../types'

export function makeResult(overrides: Partial<StructuredResult> = {}): StructuredResult {
  const node = {
    node_id: 'old-1', node_type: 'CLAUSE' as const, parent_id: null, own_text: 'Giá trị là 10.', section_context: null,
    number_label: '1', title: 'Điều khoản 1', warnings: [], body_offset: 0, raw_offsets_exact: true,
    source_segments: [{ page: 1, own_start: 0, own_end: 14, clean_start: 0, clean_end: 14, raw_start: 0, raw_end: 14, raw_exact: true }],
  }
  const document = { side: 'old' as const, source_type: 'PLAIN_TEXT' as const, page_count: 0, page_warnings: [], warnings: [], needs_review: false, nodes: [node] }
  return {
    old_document: document,
    new_document: { ...document, side: 'new' },
    alignments: [{
      old_node_id: 'old-1', new_node_id: 'old-1', node_type: 'CLAUSE', category: 'MODIFIED', alignment_stage: 'CLAUSE',
      parent_status: 'SAME', parent_changed: false, similarity_score: 0.9, alignment_confidence: 0.9, second_best_gap: 0.2,
      alternative_candidates: [], warnings: [], needs_review: true, word_changes: [{ type: 'replace', old_span: { start: 0, end: 6 }, new_span: { start: 0, end: 6 } }],
      old_entities: [], new_entities: [], entity_deltas: [], semantic_signals: [], review_priority: 'MEDIUM', review_reasons: ['Nội dung thay đổi'],
    }],
    config: {}, warnings: [], needs_review: true, b3_schema_version: 'b3-v1', entity_rules_version: 'b3-v1', priority_rules_version: 'b3-v1',
    ...overrides,
  }
}
