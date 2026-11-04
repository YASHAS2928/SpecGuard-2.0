import type { ExpectedResult } from '../api/types'

export interface DiffPart {
  text: string
  kind: 'same' | 'add' | 'del'
}

/** Word-level diff (longest common subsequence). Whitespace is kept as its own token. */
export function wordDiff(before: string, after: string): DiffPart[] {
  const a = before.split(/(\s+)/).filter(Boolean)
  const b = after.split(/(\s+)/).filter(Boolean)
  const table: number[][] = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0))
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      table[i]![j] = a[i] === b[j] ? table[i + 1]![j + 1]! + 1 : Math.max(table[i + 1]![j]!, table[i]![j + 1]!)
    }
  }
  const raw: DiffPart[] = []
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      raw.push({ text: a[i]!, kind: 'same' })
      i++
      j++
    } else if (table[i + 1]![j]! >= table[i]![j + 1]!) {
      raw.push({ text: a[i]!, kind: 'del' })
      i++
    } else {
      raw.push({ text: b[j]!, kind: 'add' })
      j++
    }
  }
  while (i < a.length) raw.push({ text: a[i++]!, kind: 'del' })
  while (j < b.length) raw.push({ text: b[j++]!, kind: 'add' })

  const merged: DiffPart[] = []
  for (const part of raw) {
    const last = merged[merged.length - 1]
    if (last && last.kind === part.kind) last.text += part.text
    else merged.push({ ...part })
  }
  return merged
}

export function listDiff(before: string[], after: string[]) {
  return {
    removed: before.filter((item) => !after.includes(item)),
    added: after.filter((item) => !before.includes(item)),
    kept: after.filter((item) => before.includes(item)),
  }
}

export function expectedBrief(value: ExpectedResult | null): string {
  if (!value) return '—'
  if (value.rejects) return 'rejected'
  if (value.overtime_minutes !== null) return `${value.overtime_minutes} OT min`
  if (value.paid_minutes !== null) return `${value.paid_minutes} paid min`
  return '—'
}
