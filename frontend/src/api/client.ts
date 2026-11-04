import type {
  Actor,
  AnalyzeResponse,
  AuditPage,
  ChangeImpact,
  Defect,
  DesignTestsResponse,
  MetricsOverview,
  Policy,
  Requirement,
  RequirementVersion,
  Run,
  Spec,
  TestCase,
  TestOrigin,
  TestReviewResponse,
  TestStatus,
  TestTechnique,
} from './types'

const BASE: string =
  (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '')

/** Builds a query string from the defined values only (no empty `?`). */
function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export class ApiError extends Error {
  status: number
  code: string
  details: unknown
  traceId: string | null

  constructor(
    status: number,
    code: string,
    message: string,
    details: unknown,
    traceId: string | null,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
    this.traceId = traceId
  }
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  const message = error instanceof Error ? error.message : String(error)
  return new ApiError(0, 'UNKNOWN_ERROR', message, null, null)
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(
      0,
      'NETWORK_ERROR',
      `Cannot reach the API at ${BASE}. Is the backend running?`,
      null,
      null,
    )
  }

  const headerTrace = response.headers.get('X-Trace-ID')
  const text = await response.text()
  let data: unknown = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      throw new ApiError(
        response.status,
        'INVALID_RESPONSE',
        'The API returned invalid JSON.',
        null,
        headerTrace,
      )
    }
  }

  if (!response.ok) {
    const envelope = isRecord(data) && isRecord(data.error) ? data.error : null
    throw new ApiError(
      response.status,
      typeof envelope?.code === 'string' ? envelope.code : 'HTTP_ERROR',
      typeof envelope?.message === 'string' ? envelope.message : `Request failed (${response.status}).`,
      envelope?.details ?? null,
      typeof envelope?.trace_id === 'string' ? envelope.trace_id : headerTrace,
    )
  }
  if (!isRecord(data) && !Array.isArray(data)) {
    throw new ApiError(
      response.status,
      'INVALID_RESPONSE',
      'The API returned an empty or invalid response.',
      null,
      headerTrace,
    )
  }
  return data as T
}

export const api = {
  listPolicies: () => request<Policy[]>('GET', '/policies?include_all_versions=true'),

  listRequirements: () => request<Requirement[]>('GET', '/requirements'),

  createRequirement: (
    payload: { code: string; title: string; text: string; policy_ids: string[] },
    actor: Actor,
  ) => request<Requirement>('POST', '/requirements', { ...payload, ...actor }),

  createVersion: (
    requirementId: string,
    payload: { text: string; policy_ids: string[]; change_note: string | null },
    actor: Actor,
  ) =>
    request<RequirementVersion>('POST', `/requirements/${requirementId}/versions`, {
      ...payload,
      ...actor,
    }),

  analyze: (versionId: string, force: boolean, actor: Actor) =>
    request<AnalyzeResponse>('POST', `/requirement-versions/${versionId}/analyze`, {
      force,
      ...actor,
    }),

  listSpecs: (versionId: string) =>
    request<Spec[]>('GET', `/requirement-versions/${versionId}/specs`),

  getSpec: (specId: string) => request<Spec>('GET', `/specs/${specId}`),

  resolveAmbiguity: (
    ambiguityId: string,
    choice: { option_index: number } | { defer: true; comment?: string },
    actor: Actor,
  ) => request<Spec>('POST', `/ambiguities/${ambiguityId}/resolve`, { ...choice, ...actor }),

  approveSpec: (specId: string, comment: string | null, actor: Actor) =>
    request<Spec>('POST', `/specs/${specId}/approve`, {
      comment: comment || null,
      ...actor,
    }),

  // --- Part 2: tests, runs, defects, impact, overview, audit ---

  designTests: (specId: string, includeAiEdgeCases: boolean, actor: Actor) =>
    request<DesignTestsResponse>('POST', `/specs/${specId}/design-tests`, {
      include_ai_edge_cases: includeAiEdgeCases,
      ...actor,
    }),

  listTests: (
    specId: string,
    filters: { status?: TestStatus; technique?: TestTechnique; origin?: TestOrigin } = {},
  ) =>
    request<TestCase[]>(
      'GET',
      `/specs/${specId}/tests${query({
        status: filters.status,
        technique: filters.technique,
        origin: filters.origin,
      })}`,
    ),

  reviewTests: (
    testIds: string[],
    decision: 'APPROVE' | 'REJECT',
    reason: string | null,
    actor: Actor,
  ) =>
    request<TestReviewResponse>('POST', '/tests/review', {
      test_ids: testIds,
      decision,
      ...(reason ? { reason } : {}),
      ...actor,
    }),

  createRun: (
    specId: string,
    testIds: string[] | null,
    trigger: 'MANUAL' | 'IMPACT_RERUN',
    actor: Actor,
  ) => request<Run>('POST', '/runs', { spec_id: specId, test_ids: testIds, trigger, ...actor }),

  getRun: (runId: string) => request<Run>('GET', `/runs/${runId}`),

  listDefects: (filters: { status?: Defect['status']; specId?: string } = {}) =>
    request<Defect[]>(
      'GET',
      `/defects${query({ status: filters.status, spec_id: filters.specId })}`,
    ),

  analyzeImpact: (newSpecId: string, fromSpecId: string, actor: Actor) =>
    request<ChangeImpact>('POST', `/specs/${newSpecId}/impact`, {
      from_spec_id: fromSpecId,
      ...actor,
    }),

  getMetrics: () => request<MetricsOverview>('GET', '/metrics/overview'),

  listAudit: (
    filters: {
      entityType?: string
      entityId?: string
      action?: string
      limit?: number
      offset?: number
    } = {},
  ) =>
    request<AuditPage>(
      'GET',
      `/audit${query({
        entity_type: filters.entityType,
        entity_id: filters.entityId,
        action: filters.action,
        limit: filters.limit,
        offset: filters.offset,
      })}`,
    ),
}
