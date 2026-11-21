import { describe, expect, it } from 'vitest'
import { buildHtmlReport, escapeHtml } from './report'
import { makeResult } from './test/fixtures'

describe('HTML report', () => {
  it('escapes contract-controlled text in every rendered field', () => {
    const result = makeResult({
      old_document: { ...makeResult().old_document, nodes: [{ ...makeResult().old_document.nodes[0], title: '<img src=x onerror=alert(1)>' }] },
    })
    const html = buildHtmlReport(result)
    expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;')
    expect(html).not.toContain('<img src=x')
    expect(html).toContain("default-src 'none'")
    expect(html).toContain('không phải tư vấn pháp lý')
    expect(html).toContain('Giá trị là 10.')
    expect(html).toContain('Trang')
  })

  it('escapes quotes and apostrophes', () => {
    expect(escapeHtml(`"><script>alert('x')</script>`)).toBe('&quot;&gt;&lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt;')
  })
})
