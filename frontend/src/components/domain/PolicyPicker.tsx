/* eslint-disable react-refresh/only-export-components */
import type { Policy } from '../../api/types'
import { inputClass } from '../ui'

export const DEFAULT_POLICY_REFS = ['POL-OT-01@v1', 'POL-MEAL-02@v1', 'POL-DATE-03@v1']

export function PolicyPicker({
  policies,
  value,
  onChange,
}: {
  policies: Policy[]
  value: string[]
  onChange: (refs: string[]) => void
}) {
  const codes = Array.from(new Set(policies.map((policy) => policy.policy_code))).sort()
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {codes.map((code) => {
        const selected = value.find((ref) => ref.startsWith(`${code}@`)) ?? ''
        return (
          <label key={code} className="block text-sm">
            <span className="mb-1 block font-mono text-xs text-fg-2">{code}</span>
            <select
              className={inputClass}
              value={selected}
              onChange={(event) =>
                onChange([
                  ...value.filter((ref) => !ref.startsWith(`${code}@`)),
                  ...(event.target.value ? [event.target.value] : []),
                ])
              }
            >
              <option value="">not attached</option>
              {policies
                .filter((policy) => policy.policy_code === code)
                .map((policy) => (
                  <option key={policy.ref} value={policy.ref}>
                    {policy.ref} (from {policy.effective_from}
                    {policy.effective_to ? ` to ${policy.effective_to}` : ''})
                  </option>
                ))}
            </select>
          </label>
        )
      })}
    </div>
  )
}
