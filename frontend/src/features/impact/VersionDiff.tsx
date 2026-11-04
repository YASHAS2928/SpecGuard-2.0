import type { RequirementVersion } from '../../api/types'
import { Pill } from '../../components/ui'
import { listDiff, wordDiff } from '../../lib/diff'

export function VersionDiff({ before, after }: { before: RequirementVersion; after: RequirementVersion }) {
  const parts = wordDiff(before.text, after.text)
  const policies = listDiff(before.policy_ids, after.policy_ids)
  const same = before.id === after.id
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Pill>version {before.version}</Pill>
        <span aria-hidden="true">→</span>
        <Pill tone="accent">version {after.version}</Pill>
        {same && <span className="text-xs text-fg-3">Both specifications use the same requirement version.</span>}
      </div>

      <section aria-label="Requirement text diff">
        <p className="mb-1 text-[10px] font-medium uppercase tracking-wider text-fg-3">Requirement text</p>
        <p className="whitespace-pre-wrap text-base leading-7">
          {parts.map((part, index) =>
            part.kind === 'same' ? (
              <span key={index}>{part.text}</span>
            ) : part.kind === 'add' ? (
              <ins key={index} className="rounded-sm bg-ok/20 px-0.5 text-fg no-underline">
                {part.text}
              </ins>
            ) : (
              <del key={index} className="rounded-sm bg-bad/20 px-0.5 text-fg">
                {part.text}
              </del>
            ),
          )}
        </p>
        {parts.every((part) => part.kind === 'same') && (
          <p className="mt-1 text-xs text-fg-3">The text is identical. Only the attached policies changed.</p>
        )}
      </section>

      <section aria-label="Policy changes">
        <p className="mb-1 text-[10px] font-medium uppercase tracking-wider text-fg-3">Attached policies</p>
        <div className="flex flex-wrap gap-1.5 font-mono text-xs">
          {policies.removed.map((ref) => (
            <span key={ref} className="rounded border border-bad/40 bg-bad/10 px-1.5 py-0.5 line-through">
              {ref}
            </span>
          ))}
          {policies.added.map((ref) => (
            <span key={ref} className="rounded border border-ok/40 bg-ok/10 px-1.5 py-0.5">
              + {ref}
            </span>
          ))}
          {policies.kept.map((ref) => (
            <span key={ref} className="rounded border border-line-strong bg-well px-1.5 py-0.5 text-fg-2">
              {ref}
            </span>
          ))}
        </div>
      </section>
    </div>
  )
}
