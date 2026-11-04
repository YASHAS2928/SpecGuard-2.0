import { describe, expect, it, vi } from 'vitest'
import { api, ApiError, toApiError } from './client'
import { actor, requirement } from '../test/fixtures'

describe('API client', () => {
  it('sends policy version query and actor fields with the expected request shape', async () => {
    const fetch = vi.fn().mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify(requirement))))
    vi.stubGlobal('fetch', fetch)
    await api.listPolicies()
    expect(fetch.mock.calls[0][0]).toBe('http://localhost:8000/policies?include_all_versions=true')
    const payload = {
      code: 'RQ-014', title: 'Overnight overtime', text: 'Calculate overtime.',
      policy_ids: ['POL-OT-01@v1'],
    }
    expect(await api.createRequirement(payload, actor)).toEqual(requirement)
    expect(fetch.mock.calls[1][1]).toMatchObject({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...payload, ...actor }),
    })
  })

  it('preserves structured blockers and trace ID', async () => {
    const details = { ungrounded_rules: ['OT_THRESHOLD'] }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: { code: 'SPEC_NOT_APPROVABLE', message: 'Approval blocked', details, trace_id: 'body-trace' },
    }), { status: 409, headers: { 'X-Trace-ID': 'header-trace' } })))
    await expect(api.approveSpec('spec-id', '', actor)).rejects.toMatchObject({
      status: 409, code: 'SPEC_NOT_APPROVABLE', details, traceId: 'body-trace',
    })
  })

  it('uses the header trace for unstructured HTTP errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', {
      status: 503, headers: { 'X-Trace-ID': 'header-trace' },
    })))
    await expect(api.listRequirements()).rejects.toMatchObject({
      status: 503, code: 'HTTP_ERROR', traceId: 'header-trace',
    })
  })

  it.each(['not json', '', 'null', '17'])('rejects invalid successful JSON: %s', async (body) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, {
      headers: { 'X-Trace-ID': 'bad-response' },
    })))
    await expect(api.listRequirements()).rejects.toMatchObject({
      code: 'INVALID_RESPONSE', traceId: 'bad-response',
    })
  })

  it('surfaces network errors without treating them as empty data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('fetch failed')))
    await expect(api.listRequirements()).rejects.toMatchObject({
      status: 0, code: 'NETWORK_ERROR',
    })
  })

  it('normalizes unknown failures and preserves ApiError instances', () => {
    const error = new ApiError(403, 'FORBIDDEN', 'Not permitted', null, 'trace')
    expect(toApiError(error)).toBe(error)
    expect(toApiError(new Error('Failure')).message).toBe('Failure')
  })
})
