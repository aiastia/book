// 项目上下文管理：跟踪当前选中的项目 ID
// 项目 ID 同时写入 cookie（SSR 可读）+ localStorage（兼容）
// 关键：cookie 让服务端渲染时也能拿到 currentProjectId，避免刷新页面报"未选择项目"
import { apiPost } from './useApi'

const PROJECT_KEY = 'moyu_current_project'
const PROJECT_INFO_KEY = 'moyu_current_project_info'
const COOKIE_KEY = 'moyu_current_project'
const INFO_COOKIE_KEY = 'moyu_current_project_info'

interface ProjectInfo {
  id: number
  title: string
  genre: string
}

// 全局响应式（所有页面共享同一个 currentProjectId）
const currentProjectId = ref<number | null>(null)
const currentProjectInfo = ref<ProjectInfo | null>(null)
// SSR/客户端共享的 cookie（useCookie 在两端都能读）
const projectIdCookie = ref<any>(null)

function initCookie() {
  // useCookie 必须在 setup 或插件上下文调用，这里延迟初始化
  if (projectIdCookie.value !== null) return
  try {
    projectIdCookie.value = useCookie<number | null>(COOKIE_KEY, {
      default: () => null,
      maxAge: 60 * 60 * 24 * 365, // 1 年
      sameSite: 'lax',
    })
  } catch {
    projectIdCookie.value = false // 标记不可用（非组件上下文）
  }
}

function loadFromStorage() {
  if (import.meta.server) return
  const id = localStorage.getItem(PROJECT_KEY)
  const info = localStorage.getItem(PROJECT_INFO_KEY)
  currentProjectId.value = id ? Number(id) : null
  currentProjectInfo.value = info ? JSON.parse(info) : null
}

export function useProject() {
  // 初始化 cookie（SSR 和客户端都拿到同一个值）
  initCookie()

  // 首次调用时同步各来源
  // 优先级：URL query > cookie > localStorage（保证 SSR 和客户端一致）
  if (currentProjectId.value === null) {
    // 记录 pid 来源：URL 是最高优先级，不应被 cookie 覆盖
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
      if (projectIdCookie.value && projectIdCookie.value !== false && projectIdCookie.value.value != null) {
        currentProjectId.value = Number(projectIdCookie.value.value)
      } else if (import.meta.client) {
        // 3) 客户端兜底：localStorage（最低优先级）
        loadFromStorage()
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
      const cookieVal = projectIdCookie.value && projectIdCookie.value !== false
        ? projectIdCookie.value.value
        : null
      if (cookieVal != null && Number(cookieVal) !== currentProjectId.value) {
        if (fromUrl) {
          // URL 优先：同步 cookie 到 URL 的值
          projectIdCookie.value.value = currentProjectId.value
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
    if (projectIdCookie.value && projectIdCookie.value !== false) {
      projectIdCookie.value.value = id
    }
  }

  function clearProject() {
    currentProjectId.value = null
    currentProjectInfo.value = null
    if (import.meta.client) {
      localStorage.removeItem(PROJECT_KEY)
      localStorage.removeItem(PROJECT_INFO_KEY)
    }
    if (projectIdCookie.value && projectIdCookie.value !== false) {
      projectIdCookie.value.value = null
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
    loadFromStorage,
    projectUrl,
  }
}
