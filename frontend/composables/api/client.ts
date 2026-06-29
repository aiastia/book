/**
 * API 基础层 — HTTP 客户端
 * 所有 domain API 模块共享此客户端
 */
import { useRuntimeConfig, navigateTo } from '#imports'

function getTokenSSR(): string | null {
  try {
    const event = useRequestEvent()
    if (!event) return null
    const cookie = event.headers?.get('cookie') || ''
    const match = cookie.match(/(?:^|;\s*)moyu_token=([^;]*)/)
    return match ? decodeURIComponent(match[1]) : null
  } catch {
    return null
  }
}

async function _fetch(path: string, opts: RequestInit = {}): Promise<any> {
  const config = useRuntimeConfig()
  const base = import.meta.server ? config.apiBase : config.public.apiBase
  const url = `${base}/api${path}`

  let token = ''
  if (import.meta.client) {
    token = localStorage.getItem('moyu_token') || ''
  } else {
    token = getTokenSSR() || ''
  }

  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  let res: Response
  try {
    res = await fetch(url, { ...opts, headers })
  } catch (e: any) {
    // 网络不可达（后端未启动等），抛出友好错误
    throw new Error(`网络请求失败：${e.message || '无法连接到服务器'}`)
  }
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

/**
 * SSE 流式 POST：防 Edge/CDN 超时（524）。
 * 后端用 sse_wrap 包装的端点，前端用这个调用。
 * 用法和 post() 一样，只是底层走 SSE 流（心跳保活），等 done 事件拿结果。
 */
export async function postSSE(path: string, body?: any): Promise<any> {
  const config = useRuntimeConfig()
  const base = import.meta.server ? config.apiBase : config.public.apiBase
  const url = `${base}/api${path}`

  let token = ''
  if (import.meta.client) {
    token = localStorage.getItem('moyu_token') || ''
  } else {
    token = getTokenSSR() || ''
  }

  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(url, {
    method: 'POST',
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })

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

  // 读取 SSE 流，等 done 事件
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const payload = JSON.parse(line.slice(6))
        if (payload.type === 'done') return payload.data
        if (payload.type === 'error') throw new Error(payload.message)
      }
    }
  }
  throw new Error('连接意外断开')
}

/** 从 URL 自动提取 project_id（SSR 从请求 URL query 读，客户端从 window.location 读） */
export function pid(): number {
  if (import.meta.client) {
    const m = window.location.pathname.match(/\/projects\/(\d+)/)
    if (m) return Number(m[1])
    const q = new URLSearchParams(window.location.search)
    const pid = q.get('pid')
    if (pid) return Number(pid)
  } else {
    try {
      const event = useRequestEvent()
      if (event) {
        const url = new URL(event.path, 'http://localhost')
        const qPid = url.searchParams.get('pid')
        if (qPid) return Number(qPid)
      }
    } catch { /* ignore */ }
  }
  return 0
}
