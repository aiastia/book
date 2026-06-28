/**
 * Nuxt 服务端插件：拦截 SSR 阶段的 $fetch，从请求 cookie 中读取 token
 * 并自动附加 Authorization header。与客户端 auth-fetch.client.ts 配对使用。
 */
export default defineNuxtPlugin(() => {
  const TOKEN_KEY = 'moyu_token'

  function getTokenFromCookie(): string | null {
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

  // 拦截全局 $fetch（Nuxt 底层使用 ofetch 的 globalThis.$fetch）
  const originalFetch = globalThis.$fetch
  if (originalFetch) {
    globalThis.$fetch = function (request: any, opts?: any) {
      opts = opts || {}
      opts.headers = opts.headers || {}

      // 仅在调用后端 API 时附加 token
      if (typeof request === 'string' && request.includes('/api/')) {
        const token = getTokenFromCookie()
        if (token && !opts.headers['Authorization']) {
          opts.headers['Authorization'] = `Bearer ${token}`
        }
      }

      return originalFetch(request, opts)
    } as any
  }
})
