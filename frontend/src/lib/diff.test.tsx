import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { listDiff, wordDiff } from './diff'
import { requirement } from '../test/fixtures'
import { VersionDiff } from '../features/impact/VersionDiff'

describe('wordDiff', () => {
  it('marks inserted and deleted words while retaining unchanged text', () => {
    expect(wordDiff('a c', 'a b c')).toEqual([
      { text: 'a ', kind: 'same' },
      { text: 'b ', kind: 'add' },
      { text: 'c', kind: 'same' },
    ])
    expect(wordDiff('a b c', 'a c')).toEqual([
      { text: 'a ', kind: 'same' },
      { text: 'b ', kind: 'del' },
      { text: 'c', kind: 'same' },
    ])
  })

  it('handles replacements, identical values and empty strings', () => {
    expect(wordDiff('a cat', 'a dog')).toEqual([
      { text: 'a ', kind: 'same' },
      { text: 'cat', kind: 'del' },
      { text: 'dog', kind: 'add' },
    ])
    expect(wordDiff('same text', 'same text')).toEqual([{ text: 'same text', kind: 'same' }])
    expect(wordDiff('', '')).toEqual([])
  })
})

it('computes list additions, removals and retained values', () => {
  expect(listDiff(['POL-A', 'POL-B'], ['POL-B', 'POL-C'])).toEqual({
    removed: ['POL-A'],
    added: ['POL-C'],
    kept: ['POL-B'],
  })
})

it('renders inline text changes and policy-reference chips', () => {
  const before = { ...requirement.versions[0]!, policy_ids: ['POL-OT-01@v1', 'POL-MEAL-02@v1'] }
  const after = {
    ...before,
    id: 'version-2',
    version: 2,
    text: 'Calculate overtime after 450 minutes.',
    policy_ids: ['POL-OT-01@v2', 'POL-MEAL-02@v1'],
  }
  render(<VersionDiff before={before} after={after} />)

  expect(screen.getByText('Calculate overtime')).toBeInTheDocument()
  expect(
    Array.from(document.querySelectorAll('del'))
      .map((element) => element.textContent)
      .join('')
      .replace(/\s/g, ''),
  ).toContain('foranovernightshift.')
  expect(
    Array.from(document.querySelectorAll('ins'))
      .map((element) => element.textContent)
      .join('')
      .replace(/\s/g, ''),
  ).toContain('after450minutes.')
  expect(screen.getByText('POL-OT-01@v1')).toHaveClass('line-through')
  expect(screen.getByText('+ POL-OT-01@v2')).toBeInTheDocument()
  expect(screen.getByText('POL-MEAL-02@v1')).toBeInTheDocument()
})
