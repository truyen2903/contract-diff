import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it } from 'vitest'
import { makeResult } from '../test/fixtures'
import { StructuralTree } from './StructuralTree'

it('keeps added and deleted articles with the same local ID independent', async () => {
  const user = userEvent.setup()
  const [row] = makeResult().alignments
  const result = makeResult({ alignments: [
    { ...row, node_type: 'ARTICLE', category: 'DELETED', old_node_id: 'n0001', new_node_id: null },
    { ...row, category: 'DELETED', old_node_id: 'n0002', new_node_id: null },
    { ...row, node_type: 'ARTICLE', category: 'ADDED', old_node_id: null, new_node_id: 'n0001' },
    { ...row, category: 'ADDED', old_node_id: null, new_node_id: 'n0002' },
  ] })
  render(<StructuralTree result={result} selected={0} onSelect={() => {}} />)

  await user.click(screen.getByRole('button', { name: 'Thu gọn Điều 1' }))

  expect(screen.getByRole('button', { name: 'Thu gọn Điều 3' })).toHaveAttribute('aria-expanded', 'true')
  expect(screen.getAllByRole('treeitem')).toHaveLength(3)
})
