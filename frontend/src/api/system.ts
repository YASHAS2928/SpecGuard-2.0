import { request } from './client'

export interface HealthInfo {
  status: 'ok' | 'degraded'
  app: string
  environment: string
  database: 'ok' | 'unavailable'
  ai: { provider: string; model: string | null; configured: boolean; issues: string[] }
}

export const getHealth = (): Promise<HealthInfo> => request<HealthInfo>('GET', '/health')
