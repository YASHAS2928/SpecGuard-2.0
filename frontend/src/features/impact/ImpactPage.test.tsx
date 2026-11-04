import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { loadSpecIndex } from '../../api/adapters'
import { api, ApiError } from '../../api/client'
import { analyzeImpact, loadRequirementSpecs } from '../../api/impact'
import type { ImpactReport } from '../../api/impact'
import { listSpecTests } from '../../api/tests'
import { SessionProvider } from '../../app/session'
import { WorkspaceProvider } from '../../app/workspace'
import { ToastProvider } from '../../components/ui'
import { actor, requirement, spec } from '../../test/fixtures'
import { ImpactTests, ImpactWarnings, RuleChanges } from './ImpactResult'
import ImpactPage from './ImpactPage'

vi.mock('../../api/adapters', () => ({ loadSpecIndex: vi.fn() }))
vi.mock('../../api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../api/client')>()
  return { ...original, api: { ...original.api, getSpec: vi.fn() } }
})
vi.mock('../../api/impact', () => ({
  analyzeImpact: vi.fn(),
  loadRequirementSpecs: vi.fn(),
  rerunImpacted: vi.fn(),
}))
vi.mock('../../api/tests', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../api/tests')>()
  return { ...original, listSpecTests: vi.fn() }
})

const oldVersion = { ...requirement.versions[0]!, policy_ids: ['POL-OT-01@v1'] }
const newVersion = {
  ...oldVersion,
  id: 'version-2',
  version: 2,
  text: 'Calculate overtime after 450 minutes.',
  policy_ids: ['POL-OT-01@v2'],
}
const oldSpec = { ...spec, id: 'spec-old', status: 'SUPERSEDED' as const, requirement_version_id: oldVersion.id }
const approvedSpec = {
  ...spec,
  id: 'spec-new',
  status: 'APPROVED' as const,
  requirement_version_id: newVersion.id,
  parent_spec_id: oldSpec.id,
}
const family = [
  { requirement, version: oldVersion, spec: oldSpec },
  { requirement, version: newVersion, spec: approvedSpec },
]

const report: ImpactReport = {
  id: 'impact-1',
  from_spec_id: oldSpec.id,
  to_spec_id: approvedSpec.id,
  rule_changes: [
    {
      rule_key: 'OT_THRESHOLD',
      kind: 'PARAM_CHANGED',
      before: { threshold: 480 },
      after: { threshold: 450 },
      changed_fields: ['threshold'],
    },
  ],
  impacted_criteria: ['CRIT-001'],
  impacted_tests: [
    {
      test_id: 'old-test',
      tc_code: 'TC-001',
      impact_class: 'STALE_EXPECTED',
      reason: 'The expected value changed.',
      old_expected: { paid_minutes: 480, overtime_minutes: 0, rejects: false },
      new_expected: { paid_minutes: 450, overtime_minutes: 0, rejects: false },
      replacement_test_id: 'new-test',
    },
    {
      test_id: 'new-test',
      tc_code: 'TC-002',
      impact_class: 'NEW',
      reason: 'A new boundary case.',
      old_expected: null,
      new_expected: { paid_minutes: 450, overtime_minutes: 1, rejects: false },
      replacement_test_id: null,
    },
    {
      test_id: 'same-test',
      tc_code: 'TC-003',
      impact_class: 'UNAFFECTED',
      reason: 'No expected value changed.',
      old_expected: { paid_minutes: 450, overtime_minutes: 0, rejects: false },
      new_expected: { paid_minutes: 450, overtime_minutes: 0, rejects: false },
      replacement_test_id: null,
    },
  ],
  counts: { STALE_EXPECTED: 1, OBSOLETE: 0, NEW: 1, UNAFFECTED: 1 },
  rerun_test_ids: ['new-test'],
  created_at: '2026-11-04T06:00:00Z',
  warnings: ['Tests were designed without AI edge cases.'],
}

function renderImpact(path = `/impact/${approvedSpec.id}`) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider>
        <WorkspaceProvider>
          <ToastProvider>
            <Routes>
              <Route path="/impact/:specId?" element={<ImpactPage />} />
            </Routes>
          </ToastProvider>
        </WorkspaceProvider>
      </SessionProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.resetAllMocks()
  localStorage.clear()
  vi.mocked(api.getSpec).mockResolvedValue(approvedSpec)
  vi.mocked(loadSpecIndex).mockResolvedValue(family)
  vi.mocked(loadRequirementSpecs).mockResolvedValue(family)
  vi.mocked(listSpecTests).mockResolvedValue([])
  vi.mocked(analyzeImpact).mockResolvedValue(report)
})

describe('impact components', () => {
  it('filters impacted tests and links to review tests that are not approved yet', async () => {
    const user = userEvent.setup()
    const onFilter = vi.fn()
    render(
      <MemoryRouter>
        <ImpactTests report={report} filter="" onFilter={onFilter} toSpecId={approvedSpec.id} />
      </MemoryRouter>,
    )

    await user.click(screen.getByRole('button', { name: /New\s*1/i }))
    expect(onFilter).toHaveBeenCalledWith('NEW')
    expect(screen.getByRole('link', { name: 'Test review' })).toHaveAttribute('href', `/tests/${approvedSpec.id}`)
  })

  it('shows warnings and a threshold before-to-after value', () => {
    render(
      <>
        <ImpactWarnings warnings={report.warnings} />
        <RuleChanges report={report} />
      </>,
    )
    expect(screen.getByText('Check before trusting this report')).toBeInTheDocument()
    expect(screen.getByText('Tests were designed without AI edge cases.')).toBeInTheDocument()
    expect(screen.getByText('480')).toBeInTheDocument()
    expect(screen.getByText('450')).toBeInTheDocument()
  })

  it('renders no warning banner when the API returns an empty warnings list', () => {
    const { container } = render(<ImpactWarnings warnings={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('ImpactPage', () => {
  it('disables rerun when none of the recommended test IDs are approved', async () => {
    const user = userEvent.setup()
    renderImpact()
    await user.click(await screen.findByRole('button', { name: 'Analyse impact' }))

    await waitFor(() => expect(analyzeImpact).toHaveBeenCalledWith(approvedSpec.id, oldSpec.id, actor))
    const rerun = await screen.findByRole('button', { name: 'Rerun approved recommended tests' })
    await waitFor(() => expect(rerun).toBeDisabled())
    expect(screen.getByText(/Nothing can run yet/)).toBeInTheDocument()
  })

  it('shows guidance when there is no approved specification to compare', async () => {
    vi.mocked(loadSpecIndex).mockResolvedValue([])
    renderImpact('/impact')
    expect(await screen.findByText('No approved specification to compare')).toBeInTheDocument()
  })

  it('surfaces a specification load error with its trace ID', async () => {
    vi.mocked(api.getSpec).mockRejectedValue(new ApiError(503, 'DEMO_ERROR', 'Demo unavailable', null, 'trace-123'))
    renderImpact()
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText(/Demo unavailable/)).toBeInTheDocument()
    expect(within(alert).getByText(/trace trace-123/)).toBeInTheDocument()
  })
})
