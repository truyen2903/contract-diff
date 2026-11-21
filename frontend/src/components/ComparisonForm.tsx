import { useRef, useState, type RefObject } from 'react'
import { FileUp, FileText, ArrowRight, X } from 'lucide-react'
import { ApiError, comparePdf, compareText } from '../api'
import type { StructuredResult } from '../types'
import { Alert, Button, Card } from './ui'

const MAX_FILE_BYTES = 15 * 1024 * 1024
const MAX_TEXT_CHARS = 500_000

interface ComparisonFormProps { onComplete: (result: StructuredResult) => void }

export function ComparisonForm({ onComplete }: ComparisonFormProps) {
  const [mode, setMode] = useState<'text' | 'pdf'>('text')
  const [oldText, setOldText] = useState('')
  const [newText, setNewText] = useState('')
  const [oldFile, setOldFile] = useState<File | null>(null)
  const [newFile, setNewFile] = useState<File | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const oldInput = useRef<HTMLInputElement>(null)
  const newInput = useRef<HTMLInputElement>(null)

  const validateFile = (file: File | null, label: string): string => {
    if (!file) return `Chọn ${label.toLowerCase()}.`
    if (file.size > MAX_FILE_BYTES) return `${label} vượt quá giới hạn 15 MiB.`
    return ''
  }

  async function submit() {
    setError('')
    if (mode === 'text') {
      if (!oldText.trim() || !newText.trim()) { setError('Nhập đủ nội dung phiên bản cũ và phiên bản mới.'); return }
      if (oldText.length > MAX_TEXT_CHARS || newText.length > MAX_TEXT_CHARS) { setError('Nội dung văn bản không được vượt quá 500.000 ký tự mỗi phiên bản.'); return }
    } else {
      const fileError = validateFile(oldFile, 'Phiên bản cũ') || validateFile(newFile, 'Phiên bản mới')
      if (fileError) { setError(fileError); return }
    }
    setLoading(true)
    try {
      const result = mode === 'text'
        ? await compareText(oldText, newText)
        : await comparePdf(oldFile as File, newFile as File)
      onComplete(result)
    } catch (caught) {
      setError(caught instanceof ApiError ? `${caught.message} (${caught.code})` : 'Không thể kết nối máy chủ. Kiểm tra API rồi thử lại.')
    } finally { setLoading(false) }
  }

  return <Card className="comparison-form">
    <div className="form-header"><div><p className="eyebrow">So sánh phiên bản</p><h2>Bắt đầu một lần kiểm tra</h2><p className="muted">Dữ liệu được gửi trực tiếp tới máy chủ ContractDiff đang chạy và được xử lý trong phiên tạm.</p></div><span className="privacy-note">Không lưu trong trình duyệt</span></div>
    <div className="mode-tabs" role="tablist" aria-label="Loại tài liệu">
      <button id="text-tab" role="tab" aria-selected={mode === 'text'} aria-controls="comparison-panel" className={mode === 'text' ? 'active' : ''} onClick={() => { setMode('text'); setError('') }}><FileText size={17} /> Văn bản</button>
      <button id="pdf-tab" role="tab" aria-selected={mode === 'pdf'} aria-controls="comparison-panel" className={mode === 'pdf' ? 'active' : ''} onClick={() => { setMode('pdf'); setError('') }}><FileUp size={17} /> PDF kỹ thuật số</button>
    </div>
    {error && <Alert tone="danger">{error}</Alert>}
    <div id="comparison-panel" role="tabpanel" aria-labelledby={mode === 'text' ? 'text-tab' : 'pdf-tab'} tabIndex={0}>{mode === 'text' ? <div className="text-input-grid">
      <label><span>Phiên bản cũ</span><textarea autoComplete="off" spellCheck={false} data-gramm="false" value={oldText} onChange={(event) => setOldText(event.target.value)} placeholder="Dán nội dung hợp đồng cũ…" maxLength={MAX_TEXT_CHARS} /><small>{oldText.length.toLocaleString('vi-VN')} / 500.000 ký tự</small></label>
      <label><span>Phiên bản mới</span><textarea autoComplete="off" spellCheck={false} data-gramm="false" value={newText} onChange={(event) => setNewText(event.target.value)} placeholder="Dán nội dung hợp đồng mới…" maxLength={MAX_TEXT_CHARS} /><small>{newText.length.toLocaleString('vi-VN')} / 500.000 ký tự</small></label>
    </div> : <div className="file-input-grid">
      <FileDrop label="Phiên bản cũ" file={oldFile} inputRef={oldInput} onChange={setOldFile} onClear={() => { setOldFile(null); if (oldInput.current) oldInput.current.value = '' }} />
      <FileDrop label="Phiên bản mới" file={newFile} inputRef={newInput} onChange={setNewFile} onClear={() => { setNewFile(null); if (newInput.current) newInput.current.value = '' }} />
    </div>}</div>
    <div className="form-footer"><p className="muted">PDF tối đa 15 MiB · 100 trang · văn bản trích xuất tối đa 500.000 ký tự</p><Button onClick={submit} disabled={loading}>{loading ? 'Đang xử lý…' : 'Phân tích phiên bản'} {!loading && <ArrowRight size={17} />}</Button></div>
  </Card>
}

function FileDrop({ label, file, inputRef, onChange, onClear }: { label: string; file: File | null; inputRef: RefObject<HTMLInputElement | null>; onChange: (file: File | null) => void; onClear: () => void }) {
  return <div className="file-drop"><input ref={inputRef} id={label} type="file" accept="application/pdf,.pdf" onChange={(event) => onChange(event.target.files?.[0] ?? null)} /><label htmlFor={label} className="file-drop-inner" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); onChange(event.dataTransfer.files[0] ?? null) }}><FileUp size={24} /><strong>{label}</strong>{file ? <span className="file-name">{file.name}</span> : <span>Kéo thả hoặc chọn PDF</span>}</label>{file && <button type="button" className="clear-file" aria-label={`Xóa ${label}`} onClick={onClear}><X size={16} /></button>}</div>
}
