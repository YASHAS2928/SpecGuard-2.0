import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { listAuditEvents } from '../../api/audit'
import { getMetrics } from '../../api/metrics'
import type { MetricsOverview } from '../../api/metrics'
import { loadRunHistory } from '../../api/runs'
import OverviewPage from './OverviewPage'

vi.mock('../../api/audit', () => ({ listAuditEvents: vi.fn() }))
vi.mock('../../api/metrics', () => ({ getMetrics: vi.fn() }))
vi.mock('../../api/runs', () => ({ loadRunHistory: vi.fn() }))

function metrics(overrides: Partial<MetricsOverview> = {}): MetricsOverview {
  return {
    requirements_total: 1,
    specs_approved: 1,
    ambiguities_total: 0,
    ambiguities_resolved: 0,
    requirement_completeness: 1,
    rules_total: 0,
    rules_with_passing_test: 0,
    rule_coverage: null,
    tests_by_status: { DRAFT: 0, BLOCKED: 0, APPROVED: 0, REJECTED: 0, STALE: 0, OBSOLETE: 0 },
    validation_blocks_by_code: {},
    last_run: null,
    open_defects: 0,
    tests_impacted_pending: 0,
    ai_calls_total: 0,
    ai_fallbacks_total: 0,
    generated_at: '2026-11-04T10:15:00Z',
    ...overrides,
  }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <OverviewPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(getMetrics).mockResolvedValue(metrics())
  vi.mocked(listAuditEvents).mockResolvedValue({ items: [], total: 0, limit: 8, offset: 0 })
  vi.mocked(loadRunHistory).mockResolvedValue([])
})

describe('Overview', () => {
  it('shows n/a when there is no last run', async () => {
    renderPage()

    const tile = await screen.findByRole('link', { name: /Last run pass rate/ })
    expect(tile).toHaveTextContent('n/a')
    expect(screen.getByText('no run yet')).toBeInTheDocument()
  })

  it('shows the empty state when there are no requirements', async () => {
    vi.mocked(getMetrics).mockResolvedValue(metrics({ requirements_total: 0 }))
    renderPage()

    expect(await screen.findByText('Nothing to measure yet')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'New requirement' })).toHaveAttribute('href', '/requirements?new=1')
    expect(screen.queryByText('Engineering quality')).not.toBeInTheDocument()
  })
})
