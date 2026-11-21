import type { AlignmentRow, CompactDocument, CompactNode, Entity, EntityDelta, StructuredResult } from './types'

export function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character] ?? character))
}

function entityValue(entity: Entity | null): string {
  if (!entity) return '—'
  return entity.normalized_value ?? entity.raw_text
}

function deltaHtml(delta: EntityDelta): string {
  return `<li><strong>${escapeHtml(delta.signal_type)}</strong> · ${escapeHtml(entityValue(delta.old_entity))} → ${escapeHtml(entityValue(delta.new_entity))}${delta.old_entity?.is_ambiguous || delta.new_entity?.is_ambiguous ? ' <em>cần xem lại</em>' : ''}</li>`
}

function rowLabel(row: AlignmentRow, oldDocument: CompactDocument, newDocument: CompactDocument): string {
  const oldNode = oldDocument.nodes.find((node) => node.node_id === row.old_node_id)
  const newNode = newDocument.nodes.find((node) => node.node_id === row.new_node_id)
  return oldNode?.title ?? newNode?.title ?? oldNode?.number_label ?? newNode?.number_label ?? row.node_type
}

function nodeForSide(row: AlignmentRow, side: 'old' | 'new', document: CompactDocument): CompactNode | null {
  const nodeId = side === 'old' ? row.old_node_id : row.new_node_id
  return document.nodes.find((node) => node.node_id === nodeId) ?? null
}

function pageLabel(node: CompactNode | null): string {
  if (!node) return 'Không có nguồn tương ứng'
  const pages = [...new Set(node.source_segments.map((segment) => segment.page))]
  return pages.length ? `Trang ${pages.join(', ')}` : 'Không có trang nguồn'
}

export function buildHtmlReport(result: StructuredResult, timestamp = ''): string {
  const rows = result.alignments.filter((row) => row.category !== 'UNCHANGED')
  const list = rows.map((row) => {
    const oldNode = nodeForSide(row, 'old', result.old_document)
    const newNode = nodeForSide(row, 'new', result.new_document)
    return `<article><h2>${escapeHtml(rowLabel(row, result.old_document, result.new_document))}</h2><p><strong>${escapeHtml(row.category)}</strong> · ${escapeHtml(row.review_priority)}${row.needs_review ? ' · cần xem lại' : ''}</p>${row.review_reasons.length ? `<p>${escapeHtml(row.review_reasons.join(' · '))}</p>` : ''}<div class="side-by-side"><section><h3>Phiên bản cũ · ${escapeHtml(pageLabel(oldNode))}</h3><pre>${escapeHtml(oldNode?.own_text ?? 'Không có nút tương ứng')}</pre></section><section><h3>Phiên bản mới · ${escapeHtml(pageLabel(newNode))}</h3><pre>${escapeHtml(newNode?.own_text ?? 'Không có nút tương ứng')}</pre></section></div>${row.entity_deltas.length ? `<ul>${row.entity_deltas.map(deltaHtml).join('')}</ul>` : ''}</article>`
  }).join('')
  return `<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><meta name="referrer" content="no-referrer"><title>ContractDiff · Báo cáo so sánh</title><style>body{font:16px/1.5 system-ui,sans-serif;max-width:1100px;margin:40px auto;padding:0 20px;color:#172033}article{border:1px solid #e4e8ef;border-radius:12px;padding:16px;margin:12px 0}em{color:#9a5a00}.disclaimer{background:#fff7e8;border:1px solid #f1dfb7;padding:12px;border-radius:8px;font-size:13px}.side-by-side{display:grid;grid-template-columns:1fr 1fr;gap:12px}.side-by-side section{border:1px solid #edf0f5;border-radius:8px;padding:12px}.side-by-side h3{font-size:13px;margin:0 0 8px}.side-by-side pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 ui-monospace,monospace;margin:0;color:#34445d}@media(max-width:700px){.side-by-side{grid-template-columns:1fr}}</style></head><body><h1>ContractDiff · Báo cáo so sánh</h1><p>${rows.length} thay đổi · schema ${escapeHtml(result.b3_schema_version)}${timestamp ? ` · ${escapeHtml(timestamp)}` : ''}</p><p class="disclaimer">Phân loại review chỉ là tín hiệu kỹ thuật, không phải tư vấn pháp lý.</p>${list || '<p>Hai phiên bản không có thay đổi.</p>'}<footer><small>Entity rules ${escapeHtml(result.entity_rules_version)} · Priority rules ${escapeHtml(result.priority_rules_version)}</small></footer></body></html>`
}

export function downloadHtmlReport(result: StructuredResult): void {
  if (!window.confirm('Báo cáo HTML chứa nội dung kết quả so sánh. Bạn có muốn tải xuống không?')) return
  const html = buildHtmlReport(result)
  const url = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'contractdiff-report.html'
  anchor.click()
  URL.revokeObjectURL(url)
}

export function nodeFor(row: AlignmentRow, side: 'old' | 'new', result: StructuredResult): CompactNode | null {
  const id = side === 'old' ? row.old_node_id : row.new_node_id
  const document = side === 'old' ? result.old_document : result.new_document
  return document.nodes.find((node) => node.node_id === id) ?? null
}
