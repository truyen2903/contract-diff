import type { StructuredResult } from './types'

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  readonly code: string
  readonly status: number

  constructor(message: string, status: number, code = 'REQUEST_FAILED') {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

function isStructuredResult(value: unknown): value is StructuredResult {
  if (!value || typeof value !== 'object') return false
  const result = value as Partial<StructuredResult>
  return Array.isArray(result.alignments)
    && Boolean(result.old_document && result.new_document)
    && typeof result.needs_review === 'boolean'
    && typeof result.b3_schema_version === 'string'
}

async function parseResponse(response: Response): Promise<StructuredResult> {
  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const body = data as { error_code?: string; detail?: string | { msg?: string }[] } | null
    const detail = Array.isArray(body?.detail)
      ? body.detail.map((item) => item.msg ?? 'Dữ liệu không hợp lệ').join(', ')
      : body?.detail ?? 'Không thể xử lý yêu cầu.'
    throw new ApiError(String(detail), response.status, body?.error_code ?? 'REQUEST_FAILED')
  }
  if (!isStructuredResult(data)) throw new ApiError('Phản hồi structured không hợp lệ.', 502, 'INVALID_RESPONSE')
  return data
}

export async function compareText(oldText: string, newText: string, signal?: AbortSignal): Promise<StructuredResult> {
  const response = await fetch(`${API_BASE}/api/v1/comparisons/structured/text`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ old_text: oldText, new_text: newText }),
    signal,
  })
  return parseResponse(response)
}

export async function comparePdf(oldFile: File, newFile: File, signal?: AbortSignal): Promise<StructuredResult> {
  const body = new FormData()
  body.append('old_file', oldFile, oldFile.name)
  body.append('new_file', newFile, newFile.name)
  const response = await fetch(`${API_BASE}/api/v1/comparisons/structured/pdf`, { method: 'POST', body, signal })
  return parseResponse(response)
}
