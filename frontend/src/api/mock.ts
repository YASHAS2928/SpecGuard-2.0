import { ApiError } from './client'

export const MOCK_BASE: string =
  (import.meta.env.VITE_MOCK_API_BASE_URL as string | undefined) ?? 'http://localhost:9000'

export interface MockVersionInfo {
  version: string
  available: string[]
  meal_minimum?: number
  bugs?: string[]
  ot_threshold?: number
  notes?: string
}

export const MOCK_VERSIONS: { id: string; label: string }[] = [
  { id: '1.3.0', label: '1.3.0: overnight bug (flag ignored)' },
  { id: '1.3.0-b', label: '1.3.0-b: off-by-one at the threshold' },
  { id: '1.3.0-c', label: '1.3.0-c: meal break deducted twice' },
  { id: '1.4.0', label: '1.4.0: bugs fixed (threshold 480)' },
  { id: '1.5.0', label: '1.5.0: policy v2 (threshold 450)' },
]

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${MOCK_BASE}${path}`, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(
      0,
      'MOCK_UNREACHABLE',
      `Cannot reach the mock API at ${MOCK_BASE}. Is it running, and does it allow this page's origin?`,
      null,
      null,
    )
  }
  if (!response.ok) {
    throw new ApiError(response.status, 'MOCK_ERROR', `The mock API answered HTTP ${response.status}.`, null, null)
  }
  return (await response.json()) as T
}

export const getMockVersion = (): Promise<MockVersionInfo> => call<MockVersionInfo>('GET', '/version')

export const setMockVersion = (version: string): Promise<MockVersionInfo> =>
  call<MockVersionInfo>('POST', '/admin/version', { version })
