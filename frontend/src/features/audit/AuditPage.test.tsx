import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { listAuditEvents } from '../../api/audit'
import type { AuditRecord } from '../../api/audit'
import { ApiError } from '../../api/client'
import { ToastProvider } from '../../components/ui'
import { MemoryRouter } from 'react-router-dom'
import AuditPage from './AuditPage'

vi.mock('../../api/audit', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../api/audit')>()
  return { ...original, listAuditEvents: vi.fn() }
})

function event(overrides: Partial<AuditRecord> = {}): AuditRecord {
  return {
    id: 'event-1',
    ts: '2026-11-04T06:00:00Z',
    actor: 'asha.ba',
    actor_role: 'BUSINESS_ANALYST',
    action: 'SPEC_APPROVED',
    entity_type: 'SPEC',
    entity_id: 'spec-1',
    before_hash: 'before-hash',
    after_hash: 'after-hash',
    trace_id: 'trace-123',
    detail: { comment: 'approved' },
    ...overrides,
  }
}

function renderAudit() {
  return render(
    <MemoryRouter>
      <ToastProvider>
        <AuditPage />
      </ToastProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(listAuditEvents).mockResolvedValue({
    items: [event(), event({ id: 'event-2', ts: '2026-11-03T06:00:00Z', actor: 'ravi.qa' })],
    total: 30,
    limit: 25,
    offset: 0,
  })
})

describe('AuditPage', () => {
  it('groups events by day and filters entity and action through the API', async () => {
    const user = userEvent.setup()
    renderAudit()

    const dayLabel = (iso: string) =>
      new Date(iso).toLocaleDateString(undefined, {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      })
    expect(await screen.findByRole('heading', { name: dayLabel('2026-11-04T06:00:00Z'), level: 3 })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: dayLabel('2026-11-03T06:00:00Z'), level: 3 })).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Entity type'), 'RUN')
    await user.selectOptions(screen.getByLabelText('Action'), 'RUN_EXECUTED')
    await waitFor(() => {
      expect(listAuditEvents).toHaveBeenLastCalledWith({
        entity_type: 'RUN',
        action: 'RUN_EXECUTED',
        limit: 25,
        offset: 0,
      })
    })
  })

  it('applies actor and search filtering on the loaded page and explains the scope', async () => {
    const user = userEvent.setup()
    renderAudit()
    await screen.findByText('asha.ba')
    await user.type(screen.getByLabelText('Filter by actor'), 'ravi')

    expect(screen.getByText(/Actor and search filters only apply to the 2 events on this page/)).toBeInTheDocument()
    expect(screen.queryByText('asha.ba')).not.toBeInTheDocument()
    expect(screen.getByText('ravi.qa')).toBeInTheDocument()
  })

  it('paginates with Newer and Older buttons', async () => {
    const user = userEvent.setup()
    vi.mocked(listAuditEvents).mockImplementation(async ({ offset = 0 } = {}) => ({
      items: [event({ id: `page-${offset}` })],
      total: 30,
      limit: 25,
      offset,
    }))
    renderAudit()

    await user.click(await screen.findByRole('button', { name: 'Older' }))
    await waitFor(() => expect(listAuditEvents).toHaveBeenLastCalledWith({
      entity_type: '',
      action: '',
      limit: 25,
      offset: 25,
    }))
    expect(screen.getByText('26–30 of 30')).toBeInTheDocument()
  })

  it('opens a detail drawer with hashes and trace, and closes with Escape', async () => {
    const user = userEvent.setup()
    renderAudit()
    const eventRow = await screen.findByText('asha.ba')
    await user.click(eventRow.closest('button')!)

    const drawer = screen.getByRole('dialog')
    expect(within(drawer).getByText('before-hash')).toBeInTheDocument()
    expect(within(drawer).getByText('after-hash')).toBeInTheDocument()
    expect(within(drawer).getByText('trace-123')).toBeInTheDocument()
    expect(within(drawer).getByRole('link', { name: 'Open this spec' })).toHaveAttribute('href', '/clarification/spec-1')

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('links change-impact audit records to the analyzed specification', async () => {
    const user = userEvent.setup()
    vi.mocked(listAuditEvents).mockResolvedValue({
      items: [
        event({
          action: 'CHANGE_IMPACT_ANALYZED',
          entity_type: 'CHANGE_IMPACT',
          detail: { to_spec_id: 'spec-new' },
        }),
      ],
      total: 1,
      limit: 25,
      offset: 0,
    })
    renderAudit()

    await user.click(await screen.findByText('asha.ba').then((node) => node.closest('button')!))
    expect(screen.getByRole('link', { name: 'Open this change impact' })).toHaveAttribute('href', '/impact/spec-new')
  })

  it('shows empty and API error states', async () => {
    vi.mocked(listAuditEvents).mockResolvedValueOnce({ items: [], total: 0, limit: 25, offset: 0 })
    const { unmount } = renderAudit()
    expect(await screen.findByText('Nothing has been recorded yet.')).toBeInTheDocument()
    unmount()

    vi.mocked(listAuditEvents).mockRejectedValueOnce(
      new ApiError(503, 'AUDIT_DOWN', 'Audit service unavailable', null, 'trace-audit'),
    )
    renderAudit()
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('Audit service unavailable')).toBeInTheDocument()
    expect(within(alert).getByText(/trace-audit/)).toBeInTheDocument()
  })
})
