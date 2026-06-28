/**
 * API 基础层 — HTTP 客户端
 * 所有 domain API 模块共享此客户端
 */
import { useRuntimeConfig, navigateTo } from '#imports'

async function _fetch(path: string, opts: RequestInit = {}): Promise<any> {
  const config = useRuntimeConfig()
  const base = import.meta.client ? config.public.apiBase : 'http://localhost:8000'
  const url = `${base}/api${path}`

  let token = ''
  if (import.meta.client) token = localStorage.getItem('moyu_token') || ''

  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(url, { ...opts, headers })
  if (res.status === 401) {
    if (import.meta.client) {
      localStorage.removeItem('moyu_token')
      await navigateTo('/login')
    }
    throw new Error('认证已过期')
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail.detail || detail.message || `HTTP ${res.status}`)
  }
  return res.headers.get('content-type')?.includes('application/json') ? res.json() : res.text()
}

export function get(path: string) { return _fetch(path) }
export function post(path: string, body?: any) { return _fetch(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }) }
export function put(path: string, body: any) { return _fetch(path, { method: 'PUT', body: JSON.stringify(body) }) }
export function del(path: string) { return _fetch(path, { method: 'DELETE' }) }

/** 从 URL 自动提取 project_id */
export function pid(): number {
  if (import.meta.client) {
    const m = window.location.pathname.match(/\/projects\/(\d+)/)
    if (m) return Number(m[1])
  }
  return 0
}
