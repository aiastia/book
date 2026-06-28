/**
 * Nuxt 服务端插件：拦截 SSR 阶段的 $fetch，从请求 cookie 中读取 token
 * 并自动附加 Authorization header。与客户端 auth-fetch.client.ts 配对使用。
 *
 * v2: 增加请求失败的诊断日志，方便排查 SSR 数据加载问题
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

        // SSR 诊断：记录 API 请求（仅在开发模式下）
        if (import.meta.dev) {
          const start = Date.now()
          const result = originalFetch(request, opts)
          // 对 Promise 结果附加日志
          if (result && typeof result.then === 'function') {
            return result.then(
              (data: any) => {
                const elapsed = Date.now() - start
                if (elapsed > 3000) {
                  console.warn(`[SSR fetch] 慢请求 (${elapsed}ms): ${request}`)
                }
                return data
              },
              (err: any) => {
                console.warn(
                  `[SSR fetch] 请求失败: ${request}`,
                  err?.message || err?.statusMessage || err,
                )
                throw err
              },
            )
          }
          return result
        }
      }

      return originalFetch(request, opts)
    } as any
  }
})
