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

/** 写入 cookie（SSR 可读） */
function setCookie(name: string, value: string, days = 30) {
  if (import.meta.server) return
  const expires = new Date(Date.now() + days * 86400000).toUTCString()
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; expires=${expires}; SameSite=Lax`
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
    if (import.meta.server) return
    const token = getToken()
    const raw = localStorage.getItem(USER_KEY)
    isLogged.value = !!token
    user.value = raw ? (JSON.parse(raw) as UserInfo) : null
  }

  function saveLogin(token: string, u: UserInfo) {
    setToken(token)
    setCookie(TOKEN_COOKIE, token)
    if (import.meta.client) {
      localStorage.setItem(USER_KEY, JSON.stringify(u))
    }
    isLogged.value = true
    user.value = u
  }

  function logout() {
    setToken(null)
    deleteCookie(TOKEN_COOKIE)
    if (import.meta.client) {
      localStorage.removeItem(USER_KEY)
    }
    isLogged.value = false
    user.value = null
  }

  // 客户端初始化时自动读取
  if (import.meta.client) {
    loadFromStorage()
  }

  return { isLogged, user, saveLogin, logout, loadFromStorage }
}
