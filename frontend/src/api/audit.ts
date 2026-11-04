import { request } from './client'
import type { AuditEvent, AuditPage } from './types'

export type AuditRecord = AuditEvent
export type AuditList = AuditPage

export interface AuditQuery {
  entity_type?: string
  entity_id?: string
  action?: string
  limit?: number
  offset?: number
}

export function listAuditEvents(query: AuditQuery = {}): Promise<AuditList> {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== '') params.set(key, String(value))
  }
  const suffix = params.toString()
  return request<AuditList>('GET', `/audit${suffix ? `?${suffix}` : ''}`)
}
