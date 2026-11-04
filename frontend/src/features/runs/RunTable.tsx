import { ShieldCheck } from 'lucide-react'
import type { RunResult } from '../../api/runs'
import type { TestRecord } from '../../api/tests'
import { Pill, StatusPill } from '../../components/ui'
import { expectedText } from '../../lib/tests'
import { observedText } from '../../lib/runs'

export function RunTable({
  results,
  testsById,
  onOpen,
}: {
  results: RunResult[]
  testsById: Map<string, TestRecord>
  onOpen: (id: string) => void
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[46rem] text-sm">
        <thead className="border-b border-line text-left text-[10px] uppercase tracking-wider text-fg-3">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">Test</th>
            <th scope="col" className="px-3 py-2 font-medium">Result</th>
            <th scope="col" className="px-3 py-2 font-medium">Expected (oracle)</th>
            <th scope="col" className="px-3 py-2 font-medium">Observed</th>
            <th scope="col" className="px-3 py-2 font-medium">Rules</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">ms</th>
          </tr>
        </thead>
        <tbody>
          {results.map((result) => {
            const test = testsById.get(result.test_case_id)
            const failing = result.status !== 'PASS'
            return (
              <tr
                key={result.id}
                className={`border-b border-line last:border-0 hover:bg-raised ${failing ? 'bg-bad/5' : ''}`}
              >
                <td className="px-3 py-2">
                  <button
                    type="button"
                    onClick={() => onOpen(result.id)}
                    className="font-mono text-xs font-medium text-accent hover:underline"
                  >
                    {result.tc_code}
                  </button>
                  {test && <span className="ml-2"><Pill>{test.technique}</Pill></span>}
                </td>
                <td className="px-3 py-2"><StatusPill value={result.status} /></td>
                <td className="px-3 py-2">
                  <span className="inline-flex items-center gap-1 font-mono text-xs text-prov-oracle">
                    <ShieldCheck size={12} aria-hidden="true" />
                    {test ? expectedText(test.assertion, result.expected) : '—'}
                  </span>
                </td>
                <td className={`px-3 py-2 font-mono text-xs ${failing ? 'text-bad' : 'text-fg-2'}`}>
                  {observedText(test?.assertion, result)}
                </td>
                <td
                  className="max-w-40 truncate px-3 py-2 font-mono text-xs text-fg-3"
                  title={test?.rule_keys.join(', ')}
                >
                  {test?.rule_keys.join(', ') ?? '—'}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-fg-3">{result.latency_ms ?? '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
