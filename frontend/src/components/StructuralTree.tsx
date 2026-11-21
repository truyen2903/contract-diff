import { AlertTriangle, ChevronDown, ChevronRight, FileDiff } from 'lucide-react'
import { useState } from 'react'
import type { AlignmentRow, StructuredResult } from '../types'
import { Badge, Card } from './ui'

interface StructuralTreeProps { result: StructuredResult; selected: number; onSelect: (index: number) => void }

export function StructuralTree({ result, selected, onSelect }: StructuralTreeProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const rows = result.alignments
  const visibleRows = rows.reduce<{ row: AlignmentRow; index: number; key: string; articleKey: string | null }[]>((visible, row, index) => {
    const key = `${row.old_node_id ?? ''}:${row.new_node_id ?? ''}`
    const articleKey = row.node_type === 'ARTICLE' ? key : visible.at(-1)?.articleKey ?? null
    if (row.node_type === 'ARTICLE' || !articleKey || expanded[articleKey] !== false) visible.push({ row, index, key, articleKey })
    return visible
  }, [])
  return <Card className="tree-card"><div className="panel-heading"><div><p className="eyebrow">Cấu trúc</p><h2>Cây điều khoản</h2></div><span className="count-label">{rows.length} nút</span></div><div className="tree-list" role="tree" aria-label="Cây điều khoản">{visibleRows.map(({ row, index, key }) => <TreeRow key={key} row={row} index={index} selected={index === selected} expanded={expanded[key] ?? true} onToggle={() => setExpanded((current) => ({ ...current, [key]: !(current[key] ?? true) }))} onSelect={() => onSelect(index)} />)}</div></Card>
}

function TreeRow({ row, index, selected, expanded, onToggle, onSelect }: { row: AlignmentRow; index: number; selected: boolean; expanded: boolean; onToggle: () => void; onSelect: () => void }) {
  const label = row.node_type === 'ARTICLE' ? 'Điều' : row.node_type === 'CLAUSE' ? 'Khoản' : row.node_type
  const text = row.old_entities[0]?.raw_text ?? row.new_entities[0]?.raw_text
  const level = row.node_type === 'ARTICLE' ? 1 : 2
  return <div className={`tree-row ${selected ? 'selected' : ''} tree-${row.node_type.toLowerCase()}`} role="treeitem" aria-level={level} aria-selected={selected}><button className="tree-toggle" aria-label={`${expanded ? 'Thu gọn' : 'Mở rộng'} ${label} ${index + 1}`} aria-expanded={row.node_type === 'ARTICLE' ? expanded : undefined} onClick={onToggle}>{row.node_type === 'ARTICLE' ? (expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />) : <span className="tree-dot" />}</button><button className="tree-content" onClick={onSelect}><span className="tree-line"><strong>{row.node_type === 'ARTICLE' ? row.old_node_id ?? row.new_node_id : row.node_type}</strong><Badge tone={row.category}>{row.category}</Badge>{row.needs_review && <AlertTriangle size={14} className="warning-icon" aria-label="Cần xem lại" />}</span><span className="tree-description">{text ?? `${label} ${index + 1}`} {row.semantic_signals.length > 0 && <span className="semantic-mark"><FileDiff size={12} /> {row.semantic_signals.length}</span>}</span></button></div>
}
