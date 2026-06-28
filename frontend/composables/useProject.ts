// 项目上下文管理：跟踪当前选中的项目 ID
// 项目 ID 同时写入 cookie（SSR 可读）+ localStorage（兼容）
// 关键：cookie 让服务端渲染时也能拿到 currentProjectId，避免刷新页面报"未选择项目"
// v2：使用 useState 替代 module-level ref，确保 SSR 请求间隔离，hydration 正确恢复
import { apiPost } from './useApi'

const PROJECT_KEY = 'moyu_current_project'
const PROJECT_INFO_KEY = 'moyu_current_project_info'
const COOKIE_KEY = 'moyu_current_project'
const INFO_COOKIE_KEY = 'moyu_current_project_info'
const STATE_KEY = 'moyu-project-id'
const STATE_INFO_KEY = 'moyu-project-info'
const STATE_READY_KEY = 'moyu-project-ready'

interface ProjectInfo {
  id: number
  title: string
  genre: string
}

function loadFromStorage() {
  if (import.meta.server) return
  const id = localStorage.getItem(PROJECT_KEY)
  const info = localStorage.getItem(PROJECT_INFO_KEY)
  return {
    id: id ? Number(id) : null,
    info: info ? (JSON.parse(info) as ProjectInfo) : null,
  }
}

export function useProject() {
  // 使用 useState 替代 module-level ref，确保 SSR 每个请求独立
  const currentProjectId = useState<number | null>(STATE_KEY, () => null)
  const currentProjectInfo = useState<ProjectInfo | null>(STATE_INFO_KEY, () => null)
  const projectReady = useState<boolean>(STATE_READY_KEY, () => false)

  // useCookie 每次调用返回 request-scoped 的 ref（Nuxt 内部管理生命周期）
  let projectIdCookie: any = false
  try {
    projectIdCookie = useCookie<number | null>(COOKIE_KEY, {
      default: () => null,
      maxAge: 60 * 60 * 24 * 365,
      sameSite: 'lax',
    })
  } catch {
    projectIdCookie = false
  }

  // 首次调用时初始化（useState 的 ready 标记保证只初始化一次）
  if (!projectReady.value) {
    projectReady.value = true
    let fromUrl = false

    // 1) 优先从 URL query 读取（SSR 和客户端都能读到，是最高优先级来源）
    try {
      const route = useRoute()
      const qid = route.query.pid
      if (qid && !isNaN(Number(qid))) {
        currentProjectId.value = Number(qid)
        fromUrl = true
      }
    } catch { /* 非 setup 上下文时忽略 */ }

    // 2) URL 没有 pid 时，用 cookie（SSR 可读）
    if (currentProjectId.value === null) {
      if (projectIdCookie && projectIdCookie !== false && projectIdCookie.value != null) {
        currentProjectId.value = Number(projectIdCookie.value)
      } else if (import.meta.client) {
        // 3) 客户端兜底：localStorage（最低优先级）
        const stored = loadFromStorage()
        currentProjectId.value = stored.id
        currentProjectInfo.value = stored.info
      }
    }

    // SSR: 从 cookie 加载项目信息（避免 hydration mismatch）
    if (currentProjectInfo.value === null) {
      try {
        if (import.meta.server) {
          const event = useRequestEvent()
          if (event) {
            const infoRaw = (event.headers?.get('cookie') || '').match(new RegExp(`(?:^|;\\s*)${INFO_COOKIE_KEY}=([^;]*)`))
            if (infoRaw) {
              currentProjectInfo.value = JSON.parse(decodeURIComponent(infoRaw[1]))
            }
          }
        }
      } catch { /* ignore */ }
    }

    // 客户端同步：将 cookie 和 localStorage 统一到当前权威值
    if (import.meta.client && currentProjectId.value !== null) {
      const cookieVal = projectIdCookie && projectIdCookie !== false
        ? projectIdCookie.value
        : null
      if (cookieVal != null && Number(cookieVal) !== currentProjectId.value) {
        if (fromUrl) {
          // URL 优先：同步 cookie 到 URL 的值
          if (projectIdCookie && projectIdCookie !== false) {
            projectIdCookie.value = currentProjectId.value
          }
        } else {
          // 无 URL 时 cookie 是权威值
          currentProjectId.value = Number(cookieVal)
        }
      }
      // 同步 localStorage 到当前值
      const storedId = localStorage.getItem(PROJECT_KEY)
      if (!storedId || Number(storedId) !== currentProjectId.value) {
        localStorage.setItem(PROJECT_KEY, String(currentProjectId.value))
      }
    }
  }

  function selectProject(id: number, info?: ProjectInfo) {
    currentProjectId.value = id
    if (info) {
      currentProjectInfo.value = info
      if (import.meta.client) {
        localStorage.setItem(PROJECT_INFO_KEY, JSON.stringify(info))
        document.cookie = `${INFO_COOKIE_KEY}=${encodeURIComponent(JSON.stringify(info))}; path=/; max-age=31536000; SameSite=Lax`
      }
    }
    // 同步到 cookie 和 localStorage
    if (import.meta.client) {
      localStorage.setItem(PROJECT_KEY, String(id))
    }
    if (projectIdCookie && projectIdCookie !== false) {
      projectIdCookie.value = id
    }
  }

  function clearProject() {
    currentProjectId.value = null
    currentProjectInfo.value = null
    if (import.meta.client) {
      localStorage.removeItem(PROJECT_KEY)
      localStorage.removeItem(PROJECT_INFO_KEY)
    }
    if (projectIdCookie && projectIdCookie !== false) {
      projectIdCookie.value = null
    }
  }

  /** 从 URL query 读取项目 ID（支持 ?pid=123 分享链接） */
  function syncFromQuery() {
    const route = useRoute()
    const qid = route.query.pid
    if (qid && !isNaN(Number(qid))) {
      const id = Number(qid)
      if (id !== currentProjectId.value) {
        selectProject(id)
      }
    }
  }

  /** 新建项目并设为当前项目 */
  async function createProject(title: string, genre: string = '', synopsis: string = '', options?: { target_word_count?: number; narrative_pov?: string; outline_mode?: string }) {
    const body: any = { title, genre, synopsis }
    if (options?.target_word_count) body.target_word_count = options.target_word_count
    if (options?.narrative_pov) body.narrative_pov = options.narrative_pov
    if (options?.outline_mode) body.outline_mode = options.outline_mode
    const data = await apiPost<{ id: number; title: string }>('/api/projects', body)
    selectProject(data.id, { id: data.id, title: data.title, genre })
    return data
  }

  /** 生成带项目 ID 的页面路径（用于 NuxtLink / navigateTo） */
  function projectUrl(path: string) {
    if (!currentProjectId.value) return path
    const sep = path.includes('?') ? '&' : '?'
    return `${path}${sep}pid=${currentProjectId.value}`
  }

  return {
    currentProjectId,
    currentProjectInfo,
    selectProject,
    clearProject,
    syncFromQuery,
    createProject,
    loadFromStorage: () => {
      const stored = loadFromStorage()
      if (stored.id) currentProjectId.value = stored.id
      if (stored.info) currentProjectInfo.value = stored.info
    },
    projectUrl,
  }
}
