import { describe, expect, it, vi } from 'vitest'
import { api, ApiError } from './client'
import { actor } from '../test/fixtures'

const ID = '00000000-0000-4000-8000-0000000000aa'
const OTHER = '00000000-0000-4000-8000-0000000000bb'
const BASE = 'http://localhost:8000'

interface Call {
  name: string
  invoke: () => Promise<unknown>
  method: 'GET' | 'POST'
  url: string
  body?: Record<string, unknown>
}

const calls: Call[] = [
  {
    name: 'designTests',
    invoke: () => api.designTests(ID, true, actor),
    method: 'POST',
    url: `/specs/${ID}/design-tests`,
    body: { include_ai_edge_cases: true, ...actor },
  },
  {
    name: 'listTests (no filters)',
    invoke: () => api.listTests(ID),
    method: 'GET',
    url: `/specs/${ID}/tests`,
  },
  {
    name: 'listTests (filters)',
    invoke: () => api.listTests(ID, { status: 'BLOCKED', technique: 'EDGE', origin: 'AI' }),
    method: 'GET',
    url: `/specs/${ID}/tests?status=BLOCKED&technique=EDGE&origin=AI`,
  },
  {
    name: 'reviewTests (approve)',
    invoke: () => api.reviewTests([ID, OTHER], 'APPROVE', null, actor),
    method: 'POST',
    url: '/tests/review',
    body: { test_ids: [ID, OTHER], decision: 'APPROVE', ...actor },
  },
  {
    name: 'reviewTests (reject with reason)',
    invoke: () => api.reviewTests([ID], 'REJECT', 'Duplicates TC-002.', actor),
    method: 'POST',
    url: '/tests/review',
    body: { test_ids: [ID], decision: 'REJECT', reason: 'Duplicates TC-002.', ...actor },
  },
  {
    name: 'createRun',
    invoke: () => api.createRun(ID, null, 'MANUAL', actor),
    method: 'POST',
    url: '/runs',
    body: { spec_id: ID, test_ids: null, trigger: 'MANUAL', ...actor },
  },
  {
    name: 'createRun (impact rerun of chosen tests)',
    invoke: () => api.createRun(ID, [OTHER], 'IMPACT_RERUN', actor),
    method: 'POST',
    url: '/runs',
    body: { spec_id: ID, test_ids: [OTHER], trigger: 'IMPACT_RERUN', ...actor },
  },
  { name: 'getRun', invoke: () => api.getRun(ID), method: 'GET', url: `/runs/${ID}` },
  { name: 'listDefects (none)', invoke: () => api.listDefects(), method: 'GET', url: '/defects' },
  {
    name: 'listDefects (filters)',
    invoke: () => api.listDefects({ status: 'OPEN', specId: ID }),
    method: 'GET',
    url: `/defects?status=OPEN&spec_id=${ID}`,
  },
  {
    name: 'analyzeImpact',
    invoke: () => api.analyzeImpact(ID, OTHER, actor),
    method: 'POST',
    url: `/specs/${ID}/impact`,
    body: { from_spec_id: OTHER, ...actor },
  },
  { name: 'getMetrics', invoke: () => api.getMetrics(), method: 'GET', url: '/metrics/overview' },
  { name: 'listAudit (none)', invoke: () => api.listAudit(), method: 'GET', url: '/audit' },
  {
    name: 'listAudit (filters)',
    invoke: () =>
      api.listAudit({ entityType: 'SPEC', entityId: ID, action: 'SPEC_APPROVED', limit: 50, offset: 100 }),
    method: 'GET',
    url: `/audit?entity_type=SPEC&entity_id=${ID}&action=SPEC_APPROVED&limit=50&offset=100`,
  },
]

function stubFetch(response: () => Promise<Response>) {
  const fetch = vi.fn().mockImplementation(response)
  vi.stubGlobal('fetch', fetch)
  return fetch
}

describe.each(calls)('Part 2 client: $name', (call) => {
  it('sends the expected request and returns the parsed body', async () => {
    const payload = { ok: true, marker: call.name }
    const fetch = stubFetch(() => Promise.resolve(new Response(JSON.stringify(payload))))
    expect(await call.invoke()).toEqual(payload)
    expect(fetch).toHaveBeenCalledTimes(1)
    const [url, init] = fetch.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${BASE}${call.url}`)
    expect(init.method).toBe(call.method)
    if (call.body) {
      expect(init.headers).toEqual({ 'Content-Type': 'application/json' })
      expect(JSON.parse(init.body as string)).toEqual(call.body)
    } else {
      expect(init.body).toBeUndefined()
    }
  })

  it('turns a 4xx error envelope into an ApiError with code, details and trace id', async () => {
    const details = { not_approved: [{ test_id: ID, status: 'DRAFT' }] }
    stubFetch(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            error: { code: 'CONFLICT', message: 'Only APPROVED tests can run.', details, trace_id: 'body-trace' },
          }),
          { status: 409, headers: { 'X-Trace-ID': 'header-trace' } },
        ),
      ),
    )
    const error = await call.invoke().catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 409,
      code: 'CONFLICT',
      message: 'Only APPROVED tests can run.',
      details,
      traceId: 'body-trace',
    })
  })

  it('reports an unreachable API as NETWORK_ERROR (never as empty data)', async () => {
    stubFetch(() => Promise.reject(new TypeError('fetch failed')))
    await expect(call.invoke()).rejects.toMatchObject({ status: 0, code: 'NETWORK_ERROR' })
  })
})

describe('Part 2 client: edge cases', () => {
  it('falls back to the trace header when the error body has no envelope', async () => {
    stubFetch(() =>
      Promise.resolve(new Response('{}', { status: 503, headers: { 'X-Trace-ID': 'only-header' } })),
    )
    await expect(api.getMetrics()).rejects.toMatchObject({
      status: 503,
      code: 'HTTP_ERROR',
      traceId: 'only-header',
    })
  })

  it('keeps 404 and 422 envelopes distinct', async () => {
    for (const [status, code] of [[404, 'NOT_FOUND'], [422, 'VALIDATION_ERROR']] as const) {
      stubFetch(() =>
        Promise.resolve(
          new Response(JSON.stringify({ error: { code, message: 'x', details: null, trace_id: 't' } }), { status }),
        ),
      )
      await expect(api.getRun(ID)).rejects.toMatchObject({ status, code })
    }
  })

  it('refuses an invalid successful body instead of returning it', async () => {
    stubFetch(() => Promise.resolve(new Response('not json')))
    await expect(api.listDefects()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  })
})
