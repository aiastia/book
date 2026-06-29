/** 全局 API（不依赖 project_id） */
import { get, post } from './client'

/** 灵感步骤 SSE 流式版：持续心跳保活，防 Cloudflare 524 */
async function inspirationStepStream(step: string, body: any): Promise<any> {
  const config = useRuntimeConfig()
  const base = import.meta.server ? config.apiBase : config.public.apiBase
  const url = `${base}/api/projects/global-inspiration/step/${step}/stream`
  const token = import.meta.client ? (localStorage.getItem('moyu_token') || '') : ''
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
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
  // 读取 SSE 流
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
  throw new Error('SSE 连接意外断开')
}

export const globalApi = {
  inspirationStep: (step: string, body: any) => post(`/projects/global-inspiration/step/${step}`, body),
  inspirationStepStream,
  inspirationQuickComplete: (body: any) => post('/projects/global-inspiration/quick-complete', body),
  getStats: () => get('/stats'),
  getRecentEdits: () => get('/recent-edits'),
  listWritingStyles: () => get('/writing-styles'),
}
