import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, comparePdf, compareText } from './api'
import { makeResult } from './test/fixtures'

afterEach(() => vi.restoreAllMocks())

describe('structured API client', () => {
  it('posts text and returns the real structured result', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(makeResult()), { status: 200, headers: { 'Content-Type': 'application/json' } })))
    const result = await compareText('cũ', 'mới')
    expect(result.b3_schema_version).toBe('b3-v1')
    expect(fetch).toHaveBeenCalledWith('/api/v1/comparisons/structured/text', expect.objectContaining({ method: 'POST' }))
  })

  it('maps structured and validation errors without exposing raw payloads', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error_code: 'TEXT_TOO_LONG', detail: 'Văn bản quá dài' }), { status: 422 })))
    await expect(compareText('x', 'y')).rejects.toMatchObject({ code: 'TEXT_TOO_LONG', status: 422, message: 'Văn bản quá dài' })
  })

  it('uses multipart form data for PDF comparisons', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(makeResult()), { status: 200 })))
    const oldFile = new File(['%PDF-old'], 'old.pdf', { type: 'application/pdf' })
    const newFile = new File(['%PDF-new'], 'new.pdf', { type: 'application/pdf' })
    await comparePdf(oldFile, newFile)
    const [, request] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(request.body).toBeInstanceOf(FormData)
    expect(request.headers).toBeUndefined()
  })

  it('rejects malformed success responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 200 })))
    await expect(compareText('x', 'y')).rejects.toBeInstanceOf(ApiError)
  })
})
