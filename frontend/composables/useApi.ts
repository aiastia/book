// 统一 API 封装：对接 Python 后端
// - SSR 期间用 runtimeConfig.apiBase（服务端私有），客户端用 public.apiBase
// - 自动注入登录 token（从 localStorage 读取）
// - GET 用 useApi（SSR 友好）；写操作用 apiPost/apiPut/apiDelete
// 用法：
//   const { data: books } = await useApi<Book[]>('/api/books', { key: 'books' })
//   await apiPost('/api/login', { username, password })

export interface UseApiOptions {
  key?: string
  server?: boolean
  lazy?: boolean
  timeout?: number
}

const TOKEN_KEY = 'moyu_token'

/** 读取本地保存的 token（仅客户端） */
export function getToken(): string | null {
  if (import.meta.server) return null
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

/** 保存/清除 token */
export function setToken(token: string | null) {
  if (import.meta.server) return
  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
}

/** SSR 阶段从请求 cookie 中读取 token */
function getTokenSSR(): string | null {
  if (import.meta.client) return null
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

/** 统一构建请求 headers（带 token） */
function buildHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = { ...extra }
  const token = import.meta.server ? getTokenSSR() : getToken()
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  return headers
}

/** GET 请求（SSR 友好，配合 useAsyncData） */
export function useApi<T = any>(url: string, opts: UseApiOptions = {}) {
  const config = useRuntimeConfig()
  const base = import.meta.server ? config.apiBase : config.public.apiBase

  return useAsyncData<T | null>(
    opts.key || url,
    async () => {
      // 跳过标记（无项目 ID 时不发请求）
      if (!url || url === '/api/_skip') return null
      return $fetch<T>(base + url, {
        timeout: opts.timeout ?? 8000,
        retry: 1,
        headers: buildHeaders(),
      }).catch((e: any) => {
        console.warn('[useApi] 请求失败', url, e?.message)
        return null
      })
    },
    { server: opts.server ?? true, lazy: opts.lazy ?? false },
  )
}

/** GET 请求（非 SSR，可在事件处理中调用） */
export async function apiGet<T = any>(url: string, opts: { timeout?: number } = {}): Promise<T> {
  const config = useRuntimeConfig()
  const base = import.meta.server ? config.apiBase : config.public.apiBase
  return await $fetch<T>(base + url, {
    timeout: opts.timeout ?? 8000,
    headers: buildHeaders(),
  })
}

/** POST 请求（写操作） */
export async function apiPost<T = any>(url: string, body: any = {}, opts: { timeout?: number } = {}): Promise<T> {
  const config = useRuntimeConfig()
  const base = import.meta.server ? config.apiBase : config.public.apiBase
  return await $fetch<T>(base + url, {
    method: 'POST',
    body,
    timeout: opts.timeout ?? 15000,
    headers: buildHeaders({ 'Content-Type': 'application/json' }),
  })
}

/** PUT 请求 */
export async function apiPut<T = any>(url: string, body: any = {}, opts: { timeout?: number } = {}): Promise<T> {
  const config = useRuntimeConfig()
  const base = import.meta.server ? config.apiBase : config.public.apiBase
  return await $fetch<T>(base + url, {
    method: 'PUT',
    body,
    timeout: opts.timeout ?? 15000,
    headers: buildHeaders({ 'Content-Type': 'application/json' }),
  })
}

/** DELETE 请求 */
export async function apiDelete<T = any>(url: string, opts: { timeout?: number } = {}): Promise<T> {
  const config = useRuntimeConfig()
  const base = import.meta.server ? config.apiBase : config.public.apiBase
  return await $fetch<T>(base + url, {
    method: 'DELETE',
    timeout: opts.timeout ?? 15000,
    headers: buildHeaders(),
  })
}