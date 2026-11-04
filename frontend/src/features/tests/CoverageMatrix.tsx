import type { Technique, TestRecord } from '../../api/tests'
import { Panel } from '../../components/ui'
import { TECHNIQUES, matrixCell } from '../../lib/tests'

export interface MatrixPick {
  rule: string
  technique: Technique | ''
}

export function CoverageMatrix({
  ruleKeys,
  tests,
  active,
  onPick,
}: {
  ruleKeys: string[]
  tests: TestRecord[]
  active: MatrixPick
  onPick: (pick: MatrixPick) => void
}) {
  return (
    <Panel
      title="Coverage: rules × techniques"
      actions={<span className="text-xs text-fg-3">approved / total, click a cell to filter</span>}
      bodyClassName="overflow-x-auto p-0"
    >
      <table className="w-full min-w-[34rem] text-sm">
        <thead>
          <tr className="border-b border-line text-left text-[10px] uppercase tracking-wider text-fg-3">
            <th className="px-3 py-2 font-medium">Rule</th>
            {TECHNIQUES.map((technique) => (
              <th key={technique} className="px-2 py-2 text-center font-medium">
                {technique}
              </th>
            ))}
            <th className="px-3 py-2 text-right font-medium">Total</th>
          </tr>
        </thead>
        <tbody>
          {ruleKeys.map((rule) => {
            const total = TECHNIQUES.reduce((sum, technique) => sum + matrixCell(tests, rule, technique).total, 0)
            return (
              <tr key={rule} className="border-b border-line last:border-0">
                <th scope="row" className="px-3 py-1.5 text-left font-mono text-xs font-medium">
                  {rule}
                </th>
                {TECHNIQUES.map((technique) => {
                  const cell = matrixCell(tests, rule, technique)
                  const selected = active.rule === rule && active.technique === technique
                  return (
                    <td key={technique} className="px-1 py-1 text-center">
                      {cell.total === 0 ? (
                        <span className="text-fg-3" aria-label="no tests">
                          ·
                        </span>
                      ) : (
                        <button
                          type="button"
                          aria-pressed={selected}
                          onClick={() => onPick(selected ? { rule: '', technique: '' } : { rule, technique })}
                          className={`min-w-12 rounded border px-1.5 py-0.5 font-mono text-xs tabular-nums ${
                            selected
                              ? 'border-accent bg-accent/15 text-fg'
                              : cell.approved === cell.total
                                ? 'border-ok/30 bg-ok/10 text-ok hover:bg-ok/20'
                                : 'border-line-strong bg-well text-fg-2 hover:bg-raised'
                          }`}
                        >
                          {cell.approved}/{cell.total}
                        </button>
                      )}
                    </td>
                  )
                })}
                <td className="px-3 py-1.5 text-right tabular-nums">
                  {total === 0 ? <span className="text-warn">no tests</span> : total}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </Panel>
  )
}
