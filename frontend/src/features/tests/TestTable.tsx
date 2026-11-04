import { AlertTriangle, ArrowDown, ArrowUp, ShieldCheck } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { TestRecord } from '../../api/tests'
import { Pill, ProvenanceBadge, StatusPill } from '../../components/ui'
import { expectedText, hasClaimMismatch, isBulkEligible } from '../../lib/tests'

type SortKey = 'tc_code' | 'technique' | 'origin' | 'status' | 'risk_score'
type Direction = 'asc' | 'desc'

function compare(a: TestRecord, b: TestRecord, key: SortKey): number {
  if (key === 'tc_code') return a.tc_code.localeCompare(b.tc_code, undefined, { numeric: true })
  if (key === 'risk_score') return (a.risk_score ?? -1) - (b.risk_score ?? -1)
  return a[key].localeCompare(b[key])
}

function SortHeader({
  label,
  column,
  sort,
  onSort,
}: {
  label: string
  column: SortKey
  sort: { key: SortKey; dir: Direction }
  onSort: (key: SortKey) => void
}) {
  const active = sort.key === column
  return (
    <th
      scope="col"
      aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
      className="px-3 py-2 text-left font-medium"
    >
      <button type="button" onClick={() => onSort(column)} className="inline-flex items-center gap-1 uppercase tracking-wider hover:text-fg">
        {label}
        {active && (sort.dir === 'asc' ? <ArrowUp size={11} aria-hidden="true" /> : <ArrowDown size={11} aria-hidden="true" />)}
      </button>
    </th>
  )
}

export function TestTable({
  tests,
  selected,
  onToggle,
  onToggleAll,
  onOpen,
}: {
  tests: TestRecord[]
  selected: Set<string>
  onToggle: (id: string) => void
  onToggleAll: (ids: string[], on: boolean) => void
  onOpen: (id: string) => void
}) {
  const [sort, setSort] = useState<{ key: SortKey; dir: Direction }>({ key: 'tc_code', dir: 'asc' })
  const sorted = useMemo(
    () =>
      [...tests].sort((a, b) => {
        const result = compare(a, b, sort.key)
        return sort.dir === 'asc' ? result : -result
      }),
    [tests, sort],
  )
  const eligibleIds = sorted.filter(isBulkEligible).map((test) => test.id)
  const allSelected = eligibleIds.length > 0 && eligibleIds.every((id) => selected.has(id))

  function onSort(key: SortKey) {
    setSort((current) => (current.key === key ? { key, dir: current.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' }))
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[52rem] text-sm">
        <thead className="border-b border-line text-[10px] text-fg-3">
          <tr>
            <th scope="col" className="w-9 px-3 py-2">
              <input
                type="checkbox"
                aria-label="Select all engine tests that can be approved in bulk"
                checked={allSelected}
                disabled={eligibleIds.length === 0}
                onChange={(event) => onToggleAll(eligibleIds, event.target.checked)}
              />
            </th>
            <SortHeader label="Test" column="tc_code" sort={sort} onSort={onSort} />
            <SortHeader label="Technique" column="technique" sort={sort} onSort={onSort} />
            <SortHeader label="Origin" column="origin" sort={sort} onSort={onSort} />
            <th scope="col" className="px-3 py-2 text-left font-medium uppercase tracking-wider">Rules</th>
            <th scope="col" className="px-3 py-2 text-left font-medium uppercase tracking-wider">Expected</th>
            <SortHeader label="Status" column="status" sort={sort} onSort={onSort} />
            <SortHeader label="Risk" column="risk_score" sort={sort} onSort={onSort} />
          </tr>
        </thead>
        <tbody>
          {sorted.map((test) => {
            const bulk = isBulkEligible(test)
            const blocks = test.issues.filter((issue) => issue.severity === 'BLOCK').length
            return (
              <tr key={test.id} className="border-b border-line last:border-0 hover:bg-raised">
                <td className="px-3 py-2">
                  <input
                    type="checkbox"
                    aria-label={`Select ${test.tc_code}`}
                    checked={selected.has(test.id)}
                    disabled={!bulk}
                    title={bulk ? undefined : test.origin === 'AI' ? 'AI tests are approved one at a time' : 'Not approvable in bulk'}
                    onChange={() => onToggle(test.id)}
                  />
                </td>
                <td className="px-3 py-2">
                  <button type="button" onClick={() => onOpen(test.id)} className="font-mono text-xs font-medium text-accent hover:underline">
                    {test.tc_code}
                  </button>
                </td>
                <td className="px-3 py-2"><Pill>{test.technique}</Pill></td>
                <td className="px-3 py-2">
                  {test.origin === 'AI' ? <ProvenanceBadge source="ai" label="AI" /> : <Pill>Engine</Pill>}
                </td>
                <td className="max-w-40 truncate px-3 py-2 font-mono text-xs text-fg-2" title={test.rule_keys.join(', ')}>
                  {test.rule_keys.join(', ')}
                </td>
                <td className="px-3 py-2">
                  <span className="inline-flex items-center gap-1 font-mono text-xs text-prov-oracle">
                    <ShieldCheck size={12} aria-hidden="true" />
                    {expectedText(test.assertion, test.expected)}
                  </span>
                  {hasClaimMismatch(test) && (
                    <span className="ml-2 inline-flex items-center gap-1 text-xs text-warn" title="The AI's claimed value differs from the oracle's">
                      <AlertTriangle size={12} aria-hidden="true" />
                      AI claim differs
                    </span>
                  )}
                </td>
                <td className="px-3 py-2">
                  <span className="inline-flex items-center gap-1.5">
                    <StatusPill value={test.status} />
                    {blocks > 0 && <Pill tone="bad">{blocks} block</Pill>}
                  </span>
                </td>
                <td className="px-3 py-2 tabular-nums text-fg-2">{test.risk_score ?? '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
