import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { loadSpecIndex } from '../../api/adapters'
import { api } from '../../api/client'
import {
  designSpecTests,
  listSpecTests,
  reviewSpecTests,
} from '../../api/tests'
import type { CriterionRecord, TestRecord } from '../../api/tests'
import { SessionProvider } from '../../app/session'
import { WorkspaceProvider } from '../../app/workspace'
import { ToastProvider } from '../../components/ui'
import { actor, requirement, spec } from '../../test/fixtures'
import { CoverageMatrix } from './CoverageMatrix'
import { ReviewDialog } from './Dialogs'
import { TestDrawer } from './TestDrawer'
import { TestTable } from './TestTable'
import TestsPage from './TestsPage'

vi.mock('../../api/adapters', () => ({
  loadSpecIndex: vi.fn(),
}))

vi.mock('../../api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../api/client')>()
  return {
    ...original,
    api: {
      getSpec: vi.fn(),
    },
  }
})

vi.mock('../../api/tests', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../api/tests')>()
  return {
    ...original,
    designSpecTests: vi.fn(),
    listSpecTests: vi.fn(),
    reviewSpecTests: vi.fn(),
  }
})

const approvedSpec = { ...spec, status: 'APPROVED' as const }

function makeTest(overrides: Partial<TestRecord> & Pick<TestRecord, 'id' | 'tc_code'>): TestRecord {
  return {
    spec_id: spec.id,
    origin: 'ENGINE',
    technique: 'BOUNDARY',
    inputs: { start_time: '22:00', end_time: '07:01', overnight: true, meal_break_minutes: 30 },
    assertion: 'OT_EQUALS',
    expected: { paid_minutes: null, overtime_minutes: 1, rejects: false },
    ai_claimed_expected: null,
    rationale: 'Tests the overtime boundary.',
    risk_score: 4,
    status: 'DRAFT',
    rule_keys: ['MEAL_DEDUCTION'],
    criterion_codes: [],
    policy_refs: ['POL-OT-01@v1'],
    issues: [],
    supersedes_id: null,
    created_at: '2026-11-04T10:15:00Z',
    ...overrides,
  }
}

const criterion: CriterionRecord = {
  id: 'criterion-1',
  spec_id: spec.id,
  crit_code: 'AC-1',
  rule_key: 'MEAL_DEDUCTION',
  given: 'A paid shift includes a meal break.',
  when: 'The calculation is requested.',
  then: 'Only a qualifying meal break is deducted.',
}

function renderPage(path = `/tests/${spec.id}`) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider>
        <WorkspaceProvider>
          <ToastProvider>
            <Routes>
              <Route path="/tests/:specId?" element={<TestsPage />} />
            </Routes>
          </ToastProvider>
        </WorkspaceProvider>
      </SessionProvider>
    </MemoryRouter>,
  )
}

function renderDrawer(test: TestRecord, canReview = true) {
  return render(
    <TestDrawer
      test={test}
      criteria={{ 'AC-1': criterion }}
      canReview={canReview}
      onClose={vi.fn()}
      onApprove={vi.fn()}
      onReject={vi.fn()}
      onLoadCriteria={vi.fn()}
    />,
  )
}

beforeEach(() => {
  vi.resetAllMocks()
  localStorage.clear()
  vi.mocked(loadSpecIndex).mockResolvedValue([{ requirement, version: requirement.versions[0]!, spec: approvedSpec }])
  vi.mocked(api.getSpec).mockResolvedValue(approvedSpec)
  vi.mocked(listSpecTests).mockResolvedValue([])
  vi.mocked(designSpecTests).mockResolvedValue({
    spec_id: spec.id,
    criteria: [criterion],
    tests: [],
    counts_by_technique: {},
    blocked_count: 0,
    ai_edge_cases: 'disabled',
    ai_message: null,
    added: 0,
    already_present: 0,
  })
  vi.mocked(reviewSpecTests).mockResolvedValue({ decision: 'APPROVE', reviewed: [], refused: [] })
})

describe('Batch 2 test review UI', () => {
  it('shows coverage counts and lets a cell filter by rule and technique', async () => {
    const user = userEvent.setup()
    const onPick = vi.fn()
    const tests = [
      makeTest({ id: '1', tc_code: 'TC-001', status: 'APPROVED' }),
      makeTest({ id: '2', tc_code: 'TC-002', status: 'DRAFT' }),
      makeTest({ id: '3', tc_code: 'TC-003', status: 'REJECTED' }),
    ]
    const { rerender } = render(
      <CoverageMatrix ruleKeys={['MEAL_DEDUCTION']} tests={tests} active={{ rule: '', technique: '' }} onPick={onPick} />,
    )

    const cell = screen.getByRole('button', { name: '1/2' })
    await user.click(cell)
    expect(onPick).toHaveBeenLastCalledWith({ rule: 'MEAL_DEDUCTION', technique: 'BOUNDARY' })

    rerender(
      <CoverageMatrix
        ruleKeys={['MEAL_DEDUCTION']}
        tests={tests}
        active={{ rule: 'MEAL_DEDUCTION', technique: 'BOUNDARY' }}
        onPick={onPick}
      />,
    )
    await user.click(screen.getByRole('button', { name: '1/2' }))
    expect(onPick).toHaveBeenLastCalledWith({ rule: '', technique: '' })
  })

  it('sorts test rows and filters them by status', async () => {
    const user = userEvent.setup()
    vi.mocked(listSpecTests).mockResolvedValue([
      makeTest({ id: '2', tc_code: 'TC-002', status: 'BLOCKED' }),
      makeTest({ id: '1', tc_code: 'TC-001', status: 'DRAFT' }),
    ])
    renderPage()

    await screen.findByRole('button', { name: 'TC-001' })
    const table = screen.getAllByRole('table')[1]!
    const rows = within(table).getAllByRole('row')
    expect(within(rows[1]!).getByRole('button', { name: 'TC-001' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Test' }))
    const descendingRows = within(table).getAllByRole('row')
    expect(within(descendingRows[1]!).getByRole('button', { name: 'TC-002' })).toBeInTheDocument()

    await user.selectOptions(screen.getByRole('combobox', { name: 'Status' }), 'DRAFT')
    expect(await screen.findByText('1 of 2 tests')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'TC-001' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'TC-002' })).not.toBeInTheDocument()
  })

  it('disables bulk selection for AI, blocked, and approved tests', () => {
    const tests = [
      makeTest({ id: 'ai', tc_code: 'TC-AI', origin: 'AI' }),
      makeTest({ id: 'blocked', tc_code: 'TC-BLOCK', status: 'BLOCKED' }),
      makeTest({ id: 'approved', tc_code: 'TC-APPROVED', status: 'APPROVED' }),
      makeTest({ id: 'draft', tc_code: 'TC-DRAFT' }),
    ]
    render(<TestTable tests={tests} selected={new Set()} onToggle={vi.fn()} onToggleAll={vi.fn()} onOpen={vi.fn()} />)

    expect(screen.getByRole('checkbox', { name: 'Select TC-AI' })).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: 'Select TC-BLOCK' })).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: 'Select TC-APPROVED' })).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: 'Select TC-DRAFT' })).toBeEnabled()
  })

  it('requires a non-whitespace reason before rejecting', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn().mockResolvedValue(undefined)
    render(<ReviewDialog open mode="reject" count={1} label="TC-001" onClose={vi.fn()} onConfirm={onConfirm} />)

    const dialog = screen.getByRole('dialog', { name: 'Reject TC-001?' })
    const reject = within(dialog).getByRole('button', { name: 'Reject' })
    expect(reject).toBeDisabled()
    await user.type(within(dialog).getByRole('textbox', { name: 'Reason (required)' }), '   ')
    expect(reject).toBeDisabled()
    await user.type(within(dialog).getByRole('textbox', { name: 'Reason (required)' }), ' duplicate case ')
    expect(reject).toBeEnabled()
    await user.click(reject)
    await waitFor(() => expect(onConfirm).toHaveBeenCalledWith('duplicate case'))
  })

  it('shows refusal test code and message after a review response', async () => {
    const user = userEvent.setup()
    const test = makeTest({ id: 'test-1', tc_code: 'TC-001', origin: 'AI' })
    vi.mocked(listSpecTests).mockResolvedValue([test])
    vi.mocked(reviewSpecTests).mockResolvedValue({
      decision: 'APPROVE',
      reviewed: [],
      refused: [{ test_id: test.id, code: 'TEST_NOT_REVIEWABLE', message: 'This test is blocked by validation.' }],
    })
    renderPage()

    await user.click(await screen.findByRole('button', { name: 'TC-001' }))
    const drawer = screen.getByRole('dialog', { name: 'TC-001' })
    await user.click(within(drawer).getByRole('button', { name: 'Approve' }))
    const confirmation = screen.getByRole('dialog', { name: 'Approve TC-001?' })
    await user.click(within(confirmation).getByRole('button', { name: 'Approve' }))

    const refusal = await screen.findByRole('alert')
    expect(within(refusal).getByText('TC-001')).toBeInTheDocument()
    expect(within(refusal).getByText(/This test is blocked by validation\./)).toBeInTheDocument()
  })

  it('shows oracle and AI expected blocks, mismatch details, and validation issues in the drawer', () => {
    const test = makeTest({
      id: 'ai-test',
      tc_code: 'TC-AI-001',
      origin: 'AI',
      ai_claimed_expected: { paid_minutes: null, overtime_minutes: 2, rejects: false },
      criterion_codes: ['AC-1'],
      issues: [
        {
          code: 'V08_AI_CLAIM_MISMATCH',
          severity: 'WARN',
          entity_type: 'TEST_CASE',
          entity_id: 'ai-test',
          message: 'The AI claim differs from the oracle result.',
          field_path: 'ai_claimed_expected',
          detail: null,
        },
        {
          code: 'V07_ORACLE_ERROR',
          severity: 'BLOCK',
          entity_type: 'TEST_CASE',
          entity_id: 'ai-test',
          message: 'The oracle cannot calculate this case.',
          field_path: 'inputs.start_time',
          detail: null,
        },
      ],
    })
    renderDrawer(test)

    const drawer = screen.getByRole('dialog', { name: 'TC-AI-001' })
    expect(within(drawer).getByText('Given')).toBeInTheDocument()
    expect(within(drawer).getByText('Oracle · expected')).toBeInTheDocument()
    expect(within(drawer).getByText('AI · claimed')).toBeInTheDocument()
    expect(within(drawer).getByText('The claim differs from the oracle. The oracle value above is the one used.')).toBeInTheDocument()
    expect(within(drawer).getByText('V08_AI_CLAIM_MISMATCH')).toBeInTheDocument()
    expect(within(drawer).getByText('V07_ORACLE_ERROR')).toBeInTheDocument()
  })

  it('disables approval for blocked tests and bulk approval for the Developer role', async () => {
    const blocked = makeTest({ id: 'blocked', tc_code: 'TC-BLOCKED', status: 'BLOCKED' })
    const { unmount } = renderDrawer(blocked)
    expect(within(screen.getByRole('dialog', { name: 'TC-BLOCKED' })).getByRole('button', { name: 'Approve' })).toBeDisabled()
    unmount()

    localStorage.setItem('specguard.actor', JSON.stringify({ ...actor, actor_role: 'DEVELOPER' }))
    vi.mocked(listSpecTests).mockResolvedValue([makeTest({ id: 'draft', tc_code: 'TC-DRAFT' })])
    renderPage()
    expect(await screen.findByRole('button', { name: 'Approve selected' })).toBeDisabled()
  })

  it('disables an individual approval when the active role is Developer', async () => {
    localStorage.setItem('specguard.actor', JSON.stringify({ ...actor, actor_role: 'DEVELOPER' }))
    vi.mocked(listSpecTests).mockResolvedValue([makeTest({ id: 'draft', tc_code: 'TC-DRAFT' })])
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: 'TC-DRAFT' }))
    expect(within(screen.getByRole('dialog', { name: 'TC-DRAFT' })).getByRole('button', { name: 'Approve' })).toBeDisabled()
  })

  it('opens the test review route with its deep-linked spec', async () => {
    vi.mocked(listSpecTests).mockResolvedValue([makeTest({ id: '1', tc_code: 'TC-001' })])
    renderPage(`/tests/${spec.id}`)

    expect(await screen.findByRole('button', { name: 'TC-001' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /RQ-014/ })).toBeInTheDocument()
  })
})
