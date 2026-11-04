import { request } from './client'
import type { MetricsOverview } from './types'

export type { MetricsOverview }

export const getMetrics = (): Promise<MetricsOverview> => request<MetricsOverview>('GET', '/metrics/overview')
