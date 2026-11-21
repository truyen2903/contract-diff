import { ExternalLink, Flag, ShieldAlert } from 'lucide-react'
import type { AlignmentRow, CompactNode, Entity, EntityDelta, StructuredResult } from '../types'
import { Badge, Card } from './ui'

export function AnalysisPanel({ result, row }: { result: StructuredResult; row: AlignmentRow }) {
  return <div className="analysis-stack"><Card><div className="panel-heading"><div><p className="eyebrow">Phân tích B3</p><h2>Tín hiệu semantic</h2></div><Badge tone={row.review_priority}>{row.review_priority}</Badge></div>{row.entity_deltas.length ? <div className="delta-list">{row.entity_deltas.map((delta, index) => <DeltaCard delta={delta} key={`${delta.signal_type}-${index}`} />)}</div> : <p className="muted">Không phát hiện thay đổi semantic trên nút này.</p>}</Card><Card><div className="panel-heading"><div><p className="eyebrow">Cần hành động</p><h2>Review</h2></div><Flag size={18} className={row.needs_review ? 'critical-icon' : 'muted-icon'} /></div>{row.needs_review ? <div className="review-box"><ShieldAlert size={18} /><div><strong>Cần người xem lại</strong><ul>{row.review_reasons.length ? row.review_reasons.map((reason) => <li key={reason}>{reason}</li>) : <li>Có cảnh báo từ pipeline.</li>}</ul></div></div> : <p className="muted">Không có cờ review trên bản ghi này.</p>}<div className="provenance-line"><ExternalLink size={14} /> {sourcePages(row, result)}</div></Card></div>
}

function DeltaCard({ delta }: { delta: EntityDelta }) {
  const oldValue = entityValue(delta.old_entity)
  const newValue = entityValue(delta.new_entity)
  const ambiguous = delta.old_entity?.is_ambiguous || delta.new_entity?.is_ambiguous
  return <article className="delta-card"><div className="delta-type"><span>{delta.signal_type}</span>{delta.is_value_changed ? <Badge tone="changed">Thay đổi</Badge> : <Badge tone="low">Định dạng</Badge>}</div><div className="delta-values"><span>{oldValue}</span><b>→</b><span>{newValue}</span></div><p>{delta.summary}</p>{ambiguous && <div className="ambiguity"><ShieldAlert size={14} /> {delta.old_entity?.ambiguity_reason ?? delta.new_entity?.ambiguity_reason ?? 'Giá trị mơ hồ'}</div>}</article>
}

function entityValue(entity: Entity | null): string {
  if (!entity) return '—'
  if (entity.signal_type === 'MONEY' && entity.money_amount && entity.money_currency) return `${entity.money_amount} ${entity.money_currency}`
  if (entity.signal_type === 'DURATION' && entity.duration_value) return `${entity.duration_value} ${entity.duration_unit ?? ''} ${entity.calendar_type ?? ''}`.trim()
  if (entity.signal_type === 'DATE' && entity.date_iso) return entity.date_iso
  return entity.normalized_value ?? entity.raw_text
}

function sourcePages(row: AlignmentRow, result: StructuredResult): string {
  const nodes: CompactNode[] = [row.old_node_id ? result.old_document.nodes.find((node) => node.node_id === row.old_node_id) : undefined, row.new_node_id ? result.new_document.nodes.find((node) => node.node_id === row.new_node_id) : undefined].filter((node): node is CompactNode => Boolean(node))
  const pages = [...new Set(nodes.flatMap((node) => node.source_segments.map((segment) => segment.page)))]
  return pages.length ? `Nguồn trang ${pages.join(', ')}` : 'Nguồn trang chưa có'
}
