import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from './App'

describe('ContractDiff shell', () => {
  it('opens the comparison form and validates empty text locally', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: /Tạo lần so sánh mới/i }))
    expect(screen.getByRole('heading', { name: 'So sánh hợp đồng' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Văn bản/i })).toHaveAttribute('aria-controls', 'comparison-panel')
    expect(screen.getByRole('tabpanel', { name: 'Văn bản' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Phân tích phiên bản/i }))
    expect(screen.getByText('Nhập đủ nội dung phiên bản cũ và phiên bản mới.')).toBeInTheDocument()
  })

  it('switches to PDF mode without sending a request', async () => {
    const user = userEvent.setup()
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    render(<App />)
    await user.click(screen.getByRole('button', { name: /Tạo lần so sánh mới/i }))
    await user.click(screen.getAllByRole('tab', { name: /PDF kỹ thuật số/i })[0])
    expect(screen.getAllByText('Kéo thả hoặc chọn PDF')).toHaveLength(2)
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})
