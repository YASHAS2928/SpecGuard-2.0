import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { loadSpecIndex } from '../../api/adapters'
import { api } from '../../api/client'
import { getMockVersion, setMockVersion } from '../../api/mock'
import type { DefectRecord, RunRecord, RunResult } from '../../api/runs'
import { createRun, listDefects, loadRunHistory } from '../../api/runs'
import { listSpecTests } from '../../api/tests'
import type { TestRecord } from '../../api/tests'
import { SessionProvider } from '../../app/session'
import { WorkspaceProvider } from '../../app/workspace'
import { ToastProvider } from '../../components/ui'
import { actor, requirement, spec } from '../../test/fixtures'
import { derivedPriority, observedText } from '../../lib/runs'
import { SegmentedBar, Sparkline } from '../../components/domain/Charts'
import RunsPage from './RunsPage'
import { RunTable } from './RunTable'

vi.mock('../../api/adapters', () => ({ loadSpecIndex: vi.fn() }))
vi.mock('../../api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../api/client')>()
  return { ...original, api: { getSpec: vi.fn() } }
})
vi.mock('../../api/mock', () => ({
  MOCK_BASE: 'http://localhost:9000',
  MOCK_VERSIONS: [
    { id: '1.3.0', label: '1.3.0' },
    { id: '1.4.0', label: '1.4.0' },
  ],
  getMockVersion: vi.fn(),
  setMockVersion: vi.fn(),
}))
vi.mock('../../api/runs', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../api/runs')>()
  return {
    ...original,
    createRun: vi.fn(),
    listDefects: vi.fn(),
    loadRunHistory: vi.fn(),
  }
})
vi.mock('../../api/tests', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../api/tests')>()
  return { ...original, listSpecTests: vi.fn() }
})

const approvedSpec = { ...spec, status: 'APPROVED' as const }

function makeTest(overrides: Partial<TestRecord> & Pick<TestRecord, 'id' | 'tc_code'>): TestRecord {
  return {
    spec_id: spec.id,
    origin: 'ENGINE',
    technique: 'BOUNDARY',
    inputs: { start_time: '22:00', end_time: '07:01', overnight: true, meal_break_minutes: 30 },
    assertion: 'OT_EQUALS',
    expected: { paid_minutes: null, overtime_minutes: 60, rejects: false },
    ai_claimed_expected: null,
    rationale: 'Tests the overtime boundary.',
    risk_score: 4,
    status: 'APPROVED',
    rule_keys: ['OT_THRESHOLD'],
    criterion_codes: [],
    policy_refs: ['POL-OT-01@v1'],
    issues: [],
    supersedes_id: null,
    created_at: '2026-11-04T10:15:00Z',
    ...overrides,
  }
}

function makeResult(overrides: Partial<RunResult> & Pick<RunResult, 'id' | 'tc_code' | 'test_case_id'>): RunResult {
  return {
    run_id: 'run-1',
    status: 'PASS',
    expected: { paid_minutes: null, overtime_minutes: 60, rejects: false },
    observed: { overtime_minutes: 60 },
    failed_assertion: null,
    latency_ms: 8,
    ...overrides,
  }
}

function makeRun(overrides: Partial<RunRecord> = {}): RunRecord {
  return {
    id: 'run-1',
    spec_id: spec.id,
    sut_version: '1.3.0',
    trigger: 'MANUAL',
    status: 'COMPLETED',
    started_at: '2026-11-04T10:15:00Z',
    finished_at: '2026-11-04T10:15:01Z',
    totals: { total: 2, passed: 1, failed: 1, errors: 0 },
    results: [
      makeResult({ id: 'result-pass', test_case_id: 'test-pass', tc_code: 'TC-001' }),
      makeResult({
        id: 'result-fail',
        test_case_id: 'test-fail',
        tc_code: 'TC-002',
        status: 'FAIL',
        observed: { overtime_minutes: 30 },
        failed_assertion: 'Expected 60 overtime minutes.',
      }),
    ],
    ...overrides,
  }
}

function makeDefect(overrides: Partial<DefectRecord> = {}): DefectRecord {
  return {
    id: 'defect-1',
    cluster_key: 'OT_THRESHOLD|overnight=true',
    title: 'Overnight overtime mismatch',
    rule_key: 'OT_THRESHOLD',
    partition: { overnight: true },
    status: 'OPEN',
    first_run_id: 'run-1',
    evidence_result_ids: ['result-fail'],
    hypothesis: null,
    created_at: '2026-11-04T10:15:00Z',
    ...overrides,
  }
}

function renderPage(path = `/runs/${spec.id}`) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider>
        <WorkspaceProvider>
          <ToastProvider>
            <Routes>
              <Route path="/runs/:specId?" element={<RunsPage />} />
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
  vi.mocked(loadSpecIndex).mockResolvedValue([{ requirement, version: requirement.versions[0]!, spec: approvedSpec }])
  vi.mocked(api.getSpec).mockResolvedValue(approvedSpec)
  vi.mocked(listSpecTests).mockResolvedValue([
    makeTest({ id: 'test-pass', tc_code: 'TC-001' }),
    makeTest({ id: 'test-fail', tc_code: 'TC-002' }),
  ])
  vi.mocked(listDefects).mockResolvedValue([makeDefect()])
  vi.mocked(loadRunHistory).mockResolvedValue([makeRun()])
  vi.mocked(getMockVersion).mockResolvedValue({ version: '1.3.0', meal_minimum: 30, available: ['1.3.0', '1.4.0'] })
  vi.mocked(setMockVersion).mockResolvedValue({ version: '1.4.0', available: ['1.3.0', '1.4.0'] })
})

describe('Batch 3 run and defect UI', () => {
  it('renders segmented bars and sparklines with populated and empty data', () => {
    const { rerender } = render(<SegmentedBar label="Run result" segments={[
      { label: 'passed', value: 2, className: 'bg-ok' },
      { label: 'failed', value: 1, className: 'bg-bad' },
    ]} />)
    expect(screen.getByRole('img', { name: 'Run result: 2 passed, 1 failed' })).toBeInTheDocument()
    expect(document.querySelector('.bg-ok')?.getAttribute('style')).toContain('66.666')

    rerender(<SegmentedBar label="Empty" segments={[{ label: 'none', value: 0, className: 'bg-ok' }]} />)
    expect(screen.getByRole('img', { name: 'Empty: 0 none' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Empty: 0 none' }).children).toHaveLength(0)

    rerender(<Sparkline points={[0.5, 1]} label="Pass trend" />)
    expect(screen.getByRole('img', { name: 'Pass trend' })).toBeInTheDocument()
    expect(document.querySelector('path')).toHaveAttribute('d', 'M0.0,22.0 L180.0,4.0')
    rerender(<Sparkline points={[]} label="Empty trend" />)
    expect(screen.getByText('No runs yet.')).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: 'Empty trend' })).not.toBeInTheDocument()
  })

  it('derives priority thresholds and observed text for every assertion', () => {
    expect(derivedPriority(makeDefect({ evidence_result_ids: ['a'] }))).toBe('Low')
    expect(derivedPriority(makeDefect({ evidence_result_ids: ['a', 'b'] }))).toBe('Medium')
    expect(derivedPriority(makeDefect({ evidence_result_ids: ['a', 'b', 'c'] }))).toBe('High')
    expect(observedText('PAID_EQUALS', makeResult({
      id: 'paid', test_case_id: 'paid-test', tc_code: 'TC-PAID', observed: { paid_minutes: 450 },
    }))).toBe('450 paid minutes')
    expect(observedText('OT_EQUALS', makeResult({
      id: 'ot', test_case_id: 'ot-test', tc_code: 'TC-OT', observed: { overtime_minutes: 60 },
    }))).toBe('60 overtime minutes')
    expect(observedText('REJECTS', makeResult({
      id: 'reject', test_case_id: 'reject-test', tc_code: 'TC-REJECT', observed: { status_code: 422 },
    }))).toBe('rejected (HTTP 422)')
    expect(observedText(undefined, makeResult({
      id: 'unknown', test_case_id: 'unknown-test', tc_code: 'TC-UNKNOWN',
    }))).toContain('paid')
  })

  it('shows oracle expected and observed values and highlights failures in the table', () => {
    const failure = makeResult({
      id: 'failure',
      test_case_id: 'test-fail',
      tc_code: 'TC-FAIL',
      status: 'FAIL',
      observed: { overtime_minutes: 30 },
    })
    const test = makeTest({ id: 'test-fail', tc_code: 'TC-FAIL' })
    render(<RunTable results={[failure]} testsById={new Map([[test.id, test]])} onOpen={vi.fn()} />)

    expect(screen.getByText('Expected (oracle)')).toBeInTheDocument()
    expect(screen.getByText('60 overtime minutes')).toBeInTheDocument()
    expect(screen.getByText('30 overtime minutes')).toBeInTheDocument()
    const row = screen.getByRole('row', { name: /TC-FAIL/ })
    expect(row).toHaveClass('bg-bad/5')
    expect(within(row).getByText('30 overtime minutes')).toHaveClass('text-bad')
  })

  it('requires confirmation before running and filters the table to a defect', async () => {
    const user = userEvent.setup()
    const run = makeRun()
    vi.mocked(createRun).mockResolvedValue(run)
    renderPage()

    await screen.findByRole('button', { name: 'TC-001' })
    await user.click(screen.getByRole('button', { name: 'Run approved tests' }))
    const dialog = screen.getByRole('dialog', { name: 'Run approved tests?' })
    expect(within(dialog).getByText(/2 approved test\(s\)/)).toBeInTheDocument()
    expect(dialog.textContent).toContain('mock 1.3.0')
    expect(createRun).not.toHaveBeenCalled()
    await user.click(within(dialog).getByRole('button', { name: 'Run' }))
    await waitFor(() => expect(createRun).toHaveBeenCalledWith(spec.id, null, actor))

    await user.click(screen.getByRole('button', { name: 'Show failing tests' }))
    expect(screen.getByRole('button', { name: 'TC-002' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'TC-001' })).not.toBeInTheDocument()
  })

  it('switches mock versions and shows an explicit error when the mock is unreachable', async () => {
    const user = userEvent.setup()
    const onChanged = vi.fn()
    const { MockControl } = await import('./MockControl')
    const { unmount } = render(
      <ToastProvider>
        <MockControl onChanged={onChanged} />
      </ToastProvider>,
    )
    await screen.findByText('Mock Time-to-Pay API')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Mock API version' }), '1.4.0')
    await user.click(screen.getByRole('button', { name: 'Switch' }))
    await waitFor(() => expect(setMockVersion).toHaveBeenCalledWith('1.4.0'))
    expect(onChanged).toHaveBeenCalledWith('1.4.0')
    unmount()

    vi.mocked(setMockVersion).mockRejectedValueOnce(new Error('Cannot reach the mock API'))
    render(
      <ToastProvider>
        <MockControl onChanged={vi.fn()} />
      </ToastProvider>,
    )
    await screen.findByText('Mock Time-to-Pay API')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Mock API version' }), '1.4.0')
    await user.click(screen.getByRole('button', { name: 'Switch' }))
    expect(await screen.findByText(/Cannot reach the mock API/)).toBeInTheDocument()
  })
})
