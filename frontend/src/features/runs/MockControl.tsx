import { FlaskConical } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toApiError } from '../../api/client'
import type { ApiError } from '../../api/client'
import { MOCK_BASE, MOCK_VERSIONS, getMockVersion, setMockVersion } from '../../api/mock'
import { Button, ErrorState, Panel, Pill, SkeletonRows, inputClass, useToast } from '../../components/ui'
import { useLoad } from '../../hooks'

export function MockControl({ onChanged }: { onChanged: (version: string) => void }) {
  const toast = useToast()
  const info = useLoad(() => getMockVersion(), 'mock-version')
  const [choice, setChoice] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const current = info.data?.version ?? ''
  const selected = choice || current

  useEffect(() => {
    if (current) onChanged(current)
  }, [current, onChanged])

  async function apply() {
    setBusy(true)
    setError(null)
    try {
      const updated = await setMockVersion(selected)
      onChanged(updated.version)
      toast.push({ tone: 'ok', title: `Mock API switched to ${updated.version}` })
      setChoice('')
      info.reload()
    } catch (caught) {
      setError(toApiError(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          <FlaskConical size={13} aria-hidden="true" />
          System under test
        </span>
      }
      actions={<Pill tone="warn">demo control</Pill>}
    >
      {info.loading && !info.data && <SkeletonRows rows={1} />}
      {info.error && !info.data && <ErrorState error={info.error} onRetry={info.reload} compact />}
      {info.data && (
        <div className="space-y-2">
          <p className="text-sm">
            Mock Time-to-Pay API <span className="font-mono">{current}</span>
          </p>
          {info.data.bugs && info.data.bugs.length > 0 && (
            <p className="text-xs text-warn">Seeded defect: {info.data.bugs.join(', ')}</p>
          )}
          {info.data.notes && <p className="text-xs text-fg-2">{info.data.notes}</p>}
          <p className="font-mono text-[11px] text-fg-3">
            {MOCK_BASE}
            {info.data.ot_threshold !== undefined ? ` · threshold ${info.data.ot_threshold}` : ''}
            {info.data.meal_minimum !== undefined ? ` · meal minimum ${info.data.meal_minimum}` : ''}
          </p>
          <div className="flex gap-2">
            <select
              aria-label="Mock API version"
              className={inputClass}
              value={selected}
              onChange={(event) => setChoice(event.target.value)}
            >
              {MOCK_VERSIONS.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
            <Button variant="primary" disabled={busy || selected === current} onClick={apply}>
              {busy ? 'Switching…' : 'Switch'}
            </Button>
          </div>
          {error && <ErrorState error={error} compact />}
          <p className="text-xs text-fg-3">
            Simulates a developer fixing or changing the system under test. It does not change SpecGuard.
          </p>
        </div>
      )}
    </Panel>
  )
}
