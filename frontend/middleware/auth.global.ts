// 全局路由守卫：未登录则跳转到 /login
// 同时在 SSR 和客户端阶段检查认证状态
import { getToken } from '~/composables/useApi'

// 无需登录即可访问的路径
const PUBLIC_PATHS = [
  '/login',
  '/register',
  '/about',
  '/help',
]

function isPublic(path: string): boolean {
  return PUBLIC_PATHS.some((p) => path === p || path.startsWith(p + '/'))
}

function getTokenSSR(event: any): string | null {
  // SSR 阶段从 cookie 中读取 token
  if (!event) return null
  const cookie = event.headers?.get('cookie') || ''
  const match = cookie.match(/(?:^|;\s*)moyu_token=([^;]*)/)
  return match ? decodeURIComponent(match[1]) : null
}

export default defineNuxtRouteMiddleware((to) => {
  if (isPublic(to.path)) return

  let token: string | null = null

  if (import.meta.server) {
    // SSR：从请求 cookie 中读取
    const event = useRequestEvent()
    token = getTokenSSR(event)
  } else {
    // 客户端：从 localStorage 读取
    token = getToken()
  }

  // 已登录访问登录页 → 去仪表盘
  if (token && to.path === '/login') {
    return navigateTo('/dashboard')
  }

  // 未登录访问受保护页面 → 去登录页
  if (!token) {
    return navigateTo('/login')
  }
})
