/**
 * Nuxt 插件：全局 $fetch 拦截器——自动附加 Authorization header
 */
export default defineNuxtPlugin(() => {
  const TOKEN_KEY = 'moyu_token'

  // 拦截所有 $fetch 请求（useFetch 底层走 $fetch）
  const originalFetch = globalThis.$fetch
  if (originalFetch) {
    globalThis.$fetch = function (request: any, opts?: any) {
      opts = opts || {}
      opts.headers = opts.headers || {}

      // 只在调用后端 API 时附加 token
      if (typeof request === 'string' && request.includes('/api/')) {
        const token = localStorage.getItem(TOKEN_KEY)
        if (token && !opts.headers['Authorization']) {
          opts.headers['Authorization'] = `Bearer ${token}`
        }
      }

      return originalFetch(request, opts)
    } as any
  }
})
