import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { api, ApiError } from './api/client'
import { listAuditEvents } from './api/audit'
import { SessionProvider } from './app/session'
import { WorkspaceProvider } from './app/workspace'
import { ToastProvider } from './components/ui'
import { ApproveSpecDialog } from './components/domain/ApproveSpecDialog'
import ClarificationPage from './features/clarification/ClarificationPage'
import { RequirementWorkspace } from './features/requirements/RequirementWorkspace'
import { actor, analysis, policies, requirement, spec } from './test/fixtures'

vi.mock('./api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('./api/client')>()
  return {
    ...original,
    api: {
      listPolicies: vi.fn(),
      listRequirements: vi.fn(),
      createRequirement: vi.fn(),
      createVersion: vi.fn(),
      analyze: vi.fn(),
      listSpecs: vi.fn(),
      getSpec: vi.fn(),
      resolveAmbiguity: vi.fn(),
      approveSpec: vi.fn(),
    },
  }
})

vi.mock('./api/audit', () => ({
  listAuditEvents: vi.fn(),
}))

const readySpec = {
  ...spec,
  rules: spec.rules.map((rule) => ({
    ...rule,
    grounded: true,
    unresolved_params: [],
  })),
  ambiguities: [{
    ...spec.ambiguities[0],
    status: 'OPEN' as const,
    chosen_option_index: null,
    resolved_by: null,
    resolved_at: null,
  }],
  open_ambiguities: 1,
  blocking_issue_count: 0,
}

const resolvedSpec = {
  ...readySpec,
  ambiguities: [{
    ...readySpec.ambiguities[0],
    status: 'RESOLVED' as const,
    chosen_option_index: 0,
    resolved_by: actor.actor,
    resolved_at: '2026-11-04T06:05:00Z',
  }],
  open_ambiguities: 0,
}

function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

function renderWorkspace() {
  return render(
    <MemoryRouter>
      <SessionProvider>
        <WorkspaceProvider>
          <ToastProvider>
            <RequirementWorkspace requirement={requirement} policies={policies} onChanged={vi.fn()} />
          </ToastProvider>
        </WorkspaceProvider>
      </SessionProvider>
    </MemoryRouter>,
  )
}

function renderClarification() {
  return render(
    <MemoryRouter initialEntries={[`/clarification/${spec.id}`]}>
      <SessionProvider>
        <WorkspaceProvider>
          <ToastProvider>
            <Routes>
              <Route path="/clarification/:specId" element={<ClarificationPage />} />
            </Routes>
          </ToastProvider>
        </WorkspaceProvider>
      </SessionProvider>
    </MemoryRouter>,
  )
}

function renderApprovalDialog() {
  return render(
    <SessionProvider>
      <ToastProvider>
        <ApproveSpecDialog
          open
          onClose={vi.fn()}
          spec={resolvedSpec}
          onApproved={vi.fn()}
        />
      </ToastProvider>
    </SessionProvider>,
  )
}

beforeEach(() => {
  vi.resetAllMocks()
  localStorage.clear()
  vi.mocked(api.listPolicies).mockResolvedValue(policies)
  vi.mocked(api.listRequirements).mockResolvedValue([requirement])
  vi.mocked(api.listSpecs).mockResolvedValue([readySpec])
  vi.mocked(api.getSpec).mockResolvedValue(readySpec)
  vi.mocked(listAuditEvents).mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 })
})

describe('Batch 1 requirement and clarification workflows', () => {
  it('creates a requirement from the workspace list', async () => {
    const user = userEvent.setup()
    vi.mocked(api.listRequirements).mockResolvedValueOnce([]).mockResolvedValue([requirement])
    vi.mocked(api.createRequirement).mockResolvedValue(requirement)
    vi.mocked(api.listSpecs).mockResolvedValue([])
    renderApp('/requirements')

    await user.click(await screen.findByRole('button', { name: 'New requirement' }))
    const dialog = await screen.findByRole('dialog', { name: 'New requirement' })
    await user.type(within(dialog).getByPlaceholderText('RQ-015'), 'RQ-014')
    await user.type(within(dialog).getAllByRole('textbox')[1]!, 'Overnight overtime with unpaid meal break')
    await user.type(within(dialog).getAllByRole('textbox')[2]!, 'Calculate overtime after paid hours.')
    await user.click(screen.getByRole('button', { name: 'Create requirement' }))

    await screen.findByText('Requirement RQ-014 created')
    await waitFor(() => expect(api.createRequirement).toHaveBeenCalled())
    expect(api.createRequirement).toHaveBeenCalledWith(
      {
        code: 'RQ-014',
        title: 'Overnight overtime with unpaid meal break',
        text: 'Calculate overtime after paid hours.',
        policy_ids: ['POL-OT-01@v1', 'POL-MEAL-02@v1', 'POL-DATE-03@v1'],
      },
      actor,
    )
  })

  it('analyses a requirement in RequirementWorkspace', async () => {
    const user = userEvent.setup()
    vi.mocked(api.listSpecs).mockResolvedValueOnce([]).mockResolvedValue([readySpec])
    vi.mocked(api.analyze).mockResolvedValue({ spec: readySpec, analysis })
    renderWorkspace()

    await user.click(await screen.findByRole('button', { name: 'Analyse version 1' }))
    await user.click(screen.getByRole('button', { name: 'Run analysis' }))

    await waitFor(() => expect(api.analyze).toHaveBeenCalledWith(
      requirement.versions[0].id,
      false,
      actor,
    ))
  })

  it('confirms a clarification choice and updates ClarificationPage', async () => {
    const user = userEvent.setup()
    vi.mocked(api.resolveAmbiguity).mockResolvedValue(resolvedSpec)
    renderClarification()

    await user.click((await screen.findAllByRole('button', { name: 'Choose' }))[0])
    const confirmation = await screen.findByRole('dialog', { name: /Apply interpretation/ })
    await user.click(within(confirmation).getByRole('button', { name: 'Apply' }))

    await waitFor(() => expect(api.resolveAmbiguity).toHaveBeenCalledWith(
      spec.ambiguities[0].id,
      { option_index: 0 },
      actor,
    ))
    expect(await screen.findByText('Chosen')).toBeInTheDocument()
  })

  it('confirms a deferred clarification and sends its reason', async () => {
    const user = userEvent.setup()
    const deferredSpec = {
      ...readySpec,
      ambiguities: [{ ...readySpec.ambiguities[0], status: 'DEFERRED' as const }],
    }
    vi.mocked(api.resolveAmbiguity).mockResolvedValue(deferredSpec)
    renderClarification()

    await user.click(await screen.findByRole('button', { name: 'Defer' }))
    const dialog = await screen.findByRole('dialog', { name: 'Defer AMB-1' })
    await user.type(within(dialog).getByLabelText('Reason (optional)'), 'Need policy owner input')
    await user.click(within(dialog).getByRole('button', { name: 'Defer' }))

    await waitFor(() => expect(api.resolveAmbiguity).toHaveBeenCalledWith(
      spec.ambiguities[0].id,
      { defer: true, comment: 'Need policy owner input' },
      actor,
    ))
  })

  it('shows backend approval blockers and keeps the trace ID', async () => {
    const user = userEvent.setup()
    vi.mocked(api.approveSpec).mockRejectedValue(new ApiError(
      409,
      'SPEC_NOT_APPROVABLE',
      'Approval blocked',
      { ungrounded_rules: ['MEAL_DEDUCTION'] },
      'approval-trace',
    ))
    renderApprovalDialog()
    const dialog = screen.getByRole('dialog', { name: 'Approve specification v1' })
    await user.click(within(dialog).getByRole('button', { name: 'Approve specification' }))

    expect(await screen.findByText('Rules whose source text has not been verified:')).toBeInTheDocument()
    expect(screen.getByText('SPEC_NOT_APPROVABLE · trace approval-trace')).toBeInTheDocument()
  })

  it('shows a 403 and trace ID for the DEVELOPER role', async () => {
    const user = userEvent.setup()
    localStorage.setItem('specguard.actor', JSON.stringify({ actor: 'dev.user', actor_role: 'DEVELOPER' }))
    vi.mocked(api.approveSpec).mockRejectedValue(new ApiError(
      403,
      'FORBIDDEN',
      'Role cannot approve specifications',
      null,
      'role-trace',
    ))
    renderApprovalDialog()
    const dialog = screen.getByRole('dialog', { name: 'Approve specification v1' })
    await user.click(within(dialog).getByRole('button', { name: 'Approve specification' }))

    expect(await screen.findByText('FORBIDDEN · trace role-trace')).toBeInTheDocument()
    expect(api.approveSpec).toHaveBeenCalledWith(spec.id, '', {
      actor: 'dev.user',
      actor_role: 'DEVELOPER',
    })
  })
})
