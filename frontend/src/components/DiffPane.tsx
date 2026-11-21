import type { ReactNode } from 'react'
import type { AlignmentRow, CompactNode, Span, StructuredResult } from '../types'
import { nodeFor } from '../report'

export function DiffPane({ result, row, side, mobileActive = true }: { result: StructuredResult; row: AlignmentRow; side: 'old' | 'new'; mobileActive?: boolean }) {
  const node = nodeFor(row, side, result)
  return <article className={`diff-pane ${side} ${mobileActive ? '' : 'mobile-inactive'}`}><header><div><span className="pane-kicker">{side === 'old' ? 'Phiên bản cũ' : 'Phiên bản mới'}</span><h2>{node?.title ?? node?.number_label ?? 'Không có nút tương ứng'}</h2></div><span className="source-pages">{node ? sourcePages(node) : '—'}</span></header>{node ? <div className="document-text">{renderNode(node, row, side)}</div> : <div className="missing-node">Nút này không xuất hiện ở phiên bản {side === 'old' ? 'cũ' : 'mới'}.</div>}<footer>{node?.raw_offsets_exact ? 'Ánh xạ nguồn chính xác' : 'Tham chiếu theo vùng nguồn'}{node?.warnings.length ? ` · ${node.warnings.join(' · ')}` : ''}</footer></article>
}

function sourcePages(node: CompactNode): string {
  const pages = [...new Set(node.source_segments.map((segment) => segment.page))]
  return pages.length ? `Trang ${pages.join(', ')}` : 'Không có trang'
}

function renderNode(node: CompactNode, row: AlignmentRow, side: 'old' | 'new') {
  const index = codePointToUtf16Offsets(node.own_text)
  const spans = row.word_changes.map((change) => ({
    span: side === 'old' ? change.old_span : change.new_span,
    type: change.type,
  })).filter((change): change is { span: Span; type: 'insert' | 'delete' | 'replace' } => change.span !== null && validSpan(change.span, index.length - 1)).sort((a, b) => a.span.start - b.span.start)
  if (!spans.length) return <p>{node.own_text}</p>
  const parts: ReactNode[] = []
  let cursor = 0
  spans.forEach(({ span, type }, spanIndex) => {
    const start = index[span.start]
    const end = index[span.end]
    if (start < cursor || end <= start) return
    if (start > cursor) parts.push(<span key={`plain-${spanIndex}`}>{node.own_text.slice(cursor, start)}</span>)
    const kind = side === 'old' ? type === 'delete' ? 'deleted' : 'modified' : type === 'insert' ? 'inserted' : 'modified'
    parts.push(<mark key={`change-${spanIndex}`} className={`diff-mark ${kind}`}>{node.own_text.slice(start, end)}</mark>)
    cursor = end
  })
  if (cursor < node.own_text.length) parts.push(<span key="tail">{node.own_text.slice(cursor)}</span>)
  return <p>{parts}</p>
}

function codePointToUtf16Offsets(value: string): number[] {
  const offsets = [0]
  for (const character of value) offsets.push(offsets[offsets.length - 1] + character.length)
  return offsets
}

function validSpan(span: Span, max: number): boolean {
  return Number.isInteger(span.start) && Number.isInteger(span.end) && span.start >= 0 && span.end > span.start && span.end <= max
}
