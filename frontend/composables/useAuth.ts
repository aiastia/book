// 登录态管理：保存/读取 token，判断是否已登录
// 配合 useApi 的 getToken/setToken 使用
// 同时维护 localStorage 和 cookie（SSR 可读）
import { getToken, setToken } from './useApi'

interface UserInfo {
  id: number
  username: string
  nickname: string
  is_admin?: boolean
}

const USER_KEY = 'moyu_user'
const TOKEN_COOKIE = 'moyu_token'
const USER_COOKIE = 'moyu_user'

/** 写入 cookie（SSR 可读） */
function setCookie(name: string, value: string, days = 30) {
  if (import.meta.server) return
  const expires = new Date(Date.now() + days * 86400000).toUTCString()
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; expires=${expires}; SameSite=Lax`
}

/** 读取 cookie（SSR/CSR 通用） */
function getCookie(name: string): string | null {
  if (import.meta.server) {
    // Nuxt SSR: 从 event node.req.headers.cookie 读取
    try {
      const cookies = useRequestHeaders()?.cookie
      if (!cookies) return null
      const match = cookies.match(new RegExp('(?:^|; )' + name.replace(/([.$?*|{}()[\]\\/+^])/g, '\\$1') + '=([^;]*)'))
      return match ? decodeURIComponent(match[1]) : null
    } catch {
      return null
    }
  }
  // 客户端: 从 document.cookie 读取
  const match = document.cookie.match(new RegExp('(?:^|; )' + name.replace(/([.$?*|{}()[\]\\/+^])/g, '\\$1') + '=([^;]*)'))
  return match ? decodeURIComponent(match[1]) : null
}

/** 删除 cookie */
function deleteCookie(name: string) {
  if (import.meta.server) return
  document.cookie = `${name}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`
}

export function useAuth() {
  // 响应式登录状态（仅客户端有效）
  const isLogged = ref(false)
  const user = ref<UserInfo | null>(null)

  function loadFromStorage() {
    const raw = getCookie(USER_COOKIE) || (import.meta.client ? localStorage.getItem(USER_KEY) : null)
    if (raw) {
      try {
        const u = JSON.parse(raw) as UserInfo
        user.value = u
        isLogged.value = true
      } catch {
        // ignore parse error
      }
    }
  }

  function saveLogin(token: string, u: UserInfo) {
    setToken(token)
    setCookie(TOKEN_COOKIE, token)
    setCookie(USER_COOKIE, JSON.stringify(u))
    if (import.meta.client) {
      localStorage.setItem(USER_KEY, JSON.stringify(u))
    }
    isLogged.value = true
    user.value = u
  }

  function logout() {
    setToken(null)
    deleteCookie(TOKEN_COOKIE)
    deleteCookie(USER_COOKIE)
    if (import.meta.client) {
      localStorage.removeItem(USER_KEY)
    }
    isLogged.value = false
    user.value = null
  }

  // 初始化：先从 cookie 读取用户信息（SSR + CSR 通用）
  loadFromStorage()
  // 客户端额外：从 localStorage 读取（作为 cookie 的补充/回退）
  if (import.meta.client) {
    const raw = localStorage.getItem(USER_KEY)
    if (raw && !user.value) {
      try {
        user.value = JSON.parse(raw) as UserInfo
        isLogged.value = true
      } catch {
        // ignore
      }
    }
    // 客户端再调后端验证（防止篡改）
    if (getToken()) {
      const config = useRuntimeConfig()
      const base = config.public.apiBase
      fetch(`${base}/api/auth/me`, { headers: { Authorization: `Bearer ${getToken()}` } })
        .then(r => r.ok ? r.json() : null)
        .then(u => {
          if (u?.id) {
            localStorage.setItem(USER_KEY, JSON.stringify(u))
            setCookie(USER_COOKIE, JSON.stringify(u))
            user.value = u as UserInfo
            isLogged.value = true
          }
        })
        .catch((e: any) => {
          if (e?.message !== 'Failed to fetch') console.warn('[useAuth] 验证登录态失败', e?.message)
        })
    }
  }

  return { isLogged, user, saveLogin, logout, loadFromStorage }
}
