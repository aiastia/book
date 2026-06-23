// 通用后台任务管理：对标 MuMuAINovel 的 FloatingTaskPanel。
// 支持多任务并发、轮询、取消。兼容旧的 init-task（project_init）。
//
// 任务来源：
//   1. 新通用队列 /api/tasks（BackgroundTask 表）
//   2. 旧项目初始化 /api/projects/init-task/{id}/status（ProjectInitTask 表，向下兼容）
import { apiGet, apiPost, apiDelete } from './useApi'

// 任务列表（通用队列 + 旧 init-task 合并展示）
const tasks = ref<any[]>([])
let pollTimer: any = null
let polling = false

// 旧 init-task 追踪（向下兼容 books.vue/inspire.vue 等已有代码）
const legacyTaskId = ref<number | null>(null)
const legacyTaskStatus = ref<any>(null)

function loadLegacyFromStorage() {
  if (import.meta.client) {
    const saved = localStorage.getItem('moyu_init_task')
    if (saved) {
      try {
        const parsed = JSON.parse(saved)
        if (parsed.id) {
          legacyTaskId.value = parsed.id
          if (parsed.status === 'completed' || parsed.status === 'failed') {
            legacyTaskStatus.value = parsed
            legacyTaskId.value = null
          }
        }
      } catch {}
    }
  }
}

export function useBackgroundTasks() {
  if (import.meta.client && !polling) loadLegacyFromStorage()

  // ===== 通用任务（新队列）=====
  function trackTask(task: any) {
    /** 添加一个任务到追踪列表（task 来自后端 create_task 返回 {task_id} 或完整 task dict） */
    const id = task.id ?? task.task_id
    if (!id) return
    if (tasks.value.find(t => t.id === id)) return
    tasks.value.push({
      id,
      task_type: task.task_type || 'custom',
      title: task.title || task.task_type || '任务',
      status: task.status || 'pending',
      progress: task.progress || 0,
      status_message: task.status_message || '排队中...',
      stage: task.stage || '',
      _source: 'generic',
    })
    startPolling()
  }

  async function refreshTasks() {
    // 拉取活跃的通用任务
    try {
      const list = await apiGet<any[]>('/api/tasks/active', { timeout: 5000 })
      // 合并：以服务端为准，保留本地已追踪但服务端未返回的（可能是刚创建的）
      const serverIds = new Set(list.map((t: any) => t.id))
      // 移除服务端已不活跃且本地有结果的
      tasks.value = tasks.value.filter(t => serverIds.has(t.id) || t.status === 'pending')
      // 合并服务端最新状态
      for (const st of list) {
        const existing = tasks.value.find(t => t.id === st.id)
        if (existing) {
          Object.assign(existing, st)
        } else {
          tasks.value.push({ ...st, _source: 'generic' })
        }
      }
      // 清理已完成/失败的（保留 10 秒供用户看结果）
      const now = Date.now()
      tasks.value = tasks.value.filter(t => {
        if (t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled') {
          if (!t._doneAt) t._doneAt = now
          return now - t._doneAt < 10000
        }
        return true
      })
    } catch (e) {
      // 静默失败（如未登录）
    }
  }

  // ===== 旧 init-task（向下兼容）=====
  function startLegacy(id: number) {
    legacyTaskId.value = id
    legacyTaskStatus.value = { status: 'pending', progress: 0, status_message: '排队中...' }
    if (import.meta.client) localStorage.setItem('moyu_init_task', JSON.stringify({ id }))
    startPolling()
  }

  async function pollLegacy() {
    if (!legacyTaskId.value) return
    try {
      const res = await apiGet<any>(`/api/projects/init-task/${legacyTaskId.value}/status`)
      legacyTaskStatus.value = res
      if (import.meta.client) {
        localStorage.setItem('moyu_init_task', JSON.stringify({ id: legacyTaskId.value, ...res }))
      }
      if (res.status === 'completed' || res.status === 'failed') {
        legacyTaskId.value = null
        if (import.meta.client) setTimeout(() => {
          localStorage.removeItem('moyu_init_task')
          legacyTaskStatus.value = null
        }, 10000)
      }
    } catch (e) {
      console.warn('init-task 轮询失败', e)
    }
  }

  async function poll() {
    if (polling) return
    polling = true
    try {
      await Promise.all([refreshTasks(), pollLegacy()])
    } finally {
      polling = false
    }
    // 无活跃任务则停止轮询
    if (!legacyTaskId.value && tasks.value.length === 0) {
      stopPolling()
    }
  }

  function startPolling() {
    if (pollTimer) return
    poll()
    pollTimer = setInterval(poll, 3000)
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  }

  async function cancelTask(id: number | string) {
    try {
      // legacy init-task 的 id 格式是 'legacy-{number}'
      if (typeof id === 'string' && id.startsWith('legacy-')) {
        const numericId = parseInt(id.replace('legacy-', ''))
        await apiPost(`/api/projects/init-task/${numericId}/cancel`, {})
      } else {
        await apiPost(`/api/tasks/${id}/cancel`, {})
      }
      const t = tasks.value.find(t => t.id === id)
      if (t) t.status = 'cancelled'
      // 同时更新 legacy task status
      if (legacyTaskStatus.value) {
        legacyTaskStatus.value = { ...legacyTaskStatus.value, status: 'cancelled', status_message: '任务已取消' }
      }
    } catch (e) {
      console.warn('取消失败', e)
    }
  }

  async function dismissTask(id: number | string) {
    tasks.value = tasks.value.filter(t => t.id !== id)
    // legacy task: 清除 localStorage
    if (typeof id === 'string' && id.startsWith('legacy-')) {
      if (import.meta.client) {
        localStorage.removeItem('moyu_init_task')
        legacyTaskId.value = null
        legacyTaskStatus.value = null
      }
    } else {
      try { await apiDelete(`/api/tasks/${id}`) } catch {}
    }
  }

  // 刷新页面后恢复（仅客户端）
  if (import.meta.client && !pollTimer) {
    if (legacyTaskId.value) startPolling()
    else refreshTasks().then(() => { if (tasks.value.length) startPolling() })
  }

  // 合并展示列表（通用 + 旧 init-task）
  const allTasks = computed(() => {
    const list = tasks.value.map(t => ({
      ...t,
      _isLegacy: false,
      _steps: t.progress_details?.steps || null,
    }))
    if (legacyTaskId.value || (legacyTaskStatus.value && legacyTaskStatus.value.status !== 'completed' && legacyTaskStatus.value.status !== 'failed')) {
      list.push({
        id: `legacy-${legacyTaskId.value}`,
        task_type: 'init',
        title: '项目初始化',
        status: legacyTaskStatus.value?.status || 'pending',
        progress: legacyTaskStatus.value?.progress || 0,
        status_message: legacyTaskStatus.value?.status_message || '排队中...',
        _source: 'legacy',
        _isLegacy: true,
        _steps: [
          { label: '世界观', done: legacyTaskStatus.value?.world_done },
          { label: '职业', done: legacyTaskStatus.value?.career_done },
          { label: '组织', done: legacyTaskStatus.value?.org_done },
          { label: '角色', done: legacyTaskStatus.value?.characters_done },
          { label: '职业分配', done: legacyTaskStatus.value?.assign_careers_done },
          { label: '关系', done: legacyTaskStatus.value?.relations_done },
          { label: '地点', done: legacyTaskStatus.value?.locations_done },
          { label: '物品', done: legacyTaskStatus.value?.items_done },
          { label: '大纲', done: legacyTaskStatus.value?.outline_done },
        ],
        _failedStep: legacyTaskStatus.value?.failed_step || '',
        _taskId: legacyTaskId.value,
      })
    }
    return list
  })

  const isActive = computed(() =>
    legacyTaskId.value !== null ||
    allTasks.value.some(t => t.status === 'pending' || t.status === 'running'),
  )

  return {
    tasks: allTasks,
    isActive,
    trackTask,
    startLegacy,    // 向下兼容：旧代码调 start(id)
    cancelTask,
    dismissTask,
    stopPolling,
    // 向下兼容旧 useInitTask 的返回
    taskId: legacyTaskId,
    taskStatus: legacyTaskStatus,
    message: computed(() => legacyTaskStatus.value?.status_message || ''),
    progress: computed(() => legacyTaskStatus.value?.progress || 0),
    start: startLegacy,
  }
}
