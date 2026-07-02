// 通用后台任务管理：对标 MuMuAINovel 的 FloatingTaskPanel。
// 支持多任务并发、轮询、取消。兼容旧的 init-task（project_init）。
//
// 任务来源：
//   1. 新通用队列 /api/tasks（BackgroundTask 表）
//   2. 旧项目初始化 /api/projects/init-task/{id}/status（ProjectInitTask 表，向下兼容）
import { apiGet, apiPost, apiDelete } from './useApi'

// ===== 模块级响应式状态（所有组件共享同一份数据）=====
const tasks = ref<any[]>([])
let pollTimer: any = null
let polling = false

// 旧 init-task 追踪（向下兼容 books.vue/inspire.vue 等已有代码）
const legacyTaskId = ref<number | null>(null)
const legacyTaskStatus = ref<any>(null)

// 任务完成回调注册表：{ taskTypePrefix: callback[] }
const completionCallbacks = new Map<string, Array<() => void>>()
// 已触发的任务状态，避免重复回调（形式: "task_id:progress" 或 "task_id:done"）
const triggeredStates = new Set<string>()

// WebSocket 单例
let ws: WebSocket | null = null
let wsReconnectTimer: any = null
let wsHeartbeatTimer: any = null
const WS_RECONNECT_DELAY = 5000
let wsVisibilityRegistered = false

// ===== 模块级辅助函数 =====

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

function _parseProgressDone(pd: any): number {
  if (!pd) return 0
  let details = pd
  if (typeof details === 'string') {
    try { details = JSON.parse(details) } catch { return 0 }
  }
  return details?.generation?.done || 0
}

function _applyWsUpdate(taskData: any) {
  const existing = tasks.value.find(t => t.id === taskData.id)
  if (existing) {
    const prevDone = _parseProgressDone(existing.progress_details)
    const currDone = _parseProgressDone(taskData.progress_details)
    const wasActive = existing.status === 'pending' || existing.status === 'running'
    Object.assign(existing, taskData)
    if (wasActive && (taskData.status === 'completed' || taskData.status === 'failed')) {
      existing._doneAt = Date.now()
      _fireCallbacks(taskData)
      _scheduleAutoDismiss(taskData.id)
    } else if (wasActive && currDone > prevDone) {
      _fireCallbacks(taskData)
    }
  } else {
    // 本地没有这个任务（页面刷新/路由切换后 tasks 被清空）
    // 如果收到的是一个已完成/失败的任务，仍需触发回调刷新页面数据
    tasks.value.push({ ...taskData, _source: 'generic' })
    if (taskData.status === 'completed' || taskData.status === 'failed') {
      _fireCallbacks(taskData)
      _scheduleAutoDismiss(taskData.id)
    }
  }
}

function _fireCallbacks(task: any) {
  const ttype = task.task_type || ''
  const tid = task.id
  const currentProgress = _parseProgressDone(task.progress_details) || task.progress || 0
  const isComplete = task.status === 'completed' || task.status === 'failed' || task.status === 'cancelled'
  const stateKey = `${tid}:${isComplete ? 'done' : currentProgress}`
  if (triggeredStates.has(stateKey)) return
  triggeredStates.add(stateKey)
  const cbs: Array<() => void> = []
  for (const [prefix, callbacks] of completionCallbacks.entries()) {
    if (ttype.startsWith(prefix)) {
      cbs.push(...callbacks)
    }
  }
  if (cbs.length) {
    nextTick(() => cbs.forEach(cb => { try { cb() } catch {} }))
  }
}

function _cleanupOldDoneTasks() {
  const now = Date.now()
  tasks.value = tasks.value.filter(t => {
    if (t.status === 'completed' && t._doneAt && (now - t._doneAt > AUTO_DISMISS_MS)) {
      return false
    }
    return true
  })
}

function _scheduleAutoDismiss(id: number | string) {
  const t = tasks.value.find(t => t.id === id)
  if (t && t.status === 'completed') {
    t._doneAt = Date.now()
  }
  _cleanupOldDoneTasks()
}

// ===== 模块级轮询函数 =====

async function refreshTasks() {
  _cleanupOldDoneTasks()
  try {
    const list = await apiGet<any[]>('/api/tasks/active', { timeout: 5000 })
    const serverIds = new Set(list.map((t: any) => t.id))

    for (const st of list) {
      const existing = tasks.value.find(t => t.id === st.id)
      if (existing) {
        const prevDone = _parseProgressDone(existing.progress_details)
        const currDone = _parseProgressDone(st.progress_details)
        const wasActive = existing.status === 'pending' || existing.status === 'running'
        const isDone = st.status === 'completed'
        Object.assign(existing, st)
        if (wasActive && isDone) {
          _fireCallbacks(st)
        } else if (wasActive && currDone > prevDone) {
          _fireCallbacks(st)
        }
      } else {
        // 本地没有这个任务（页面刷新后）。后端 list_active_tasks 现在会返回
        // 最近 5 分钟内完成的任务，收到时触发回调刷新页面数据。
        tasks.value.push({ ...st, _source: 'generic' })
        if (st.status === 'completed' || st.status === 'failed') {
          _fireCallbacks(st)
          _scheduleAutoDismiss(st.id)
        }
      }
    }

    const staleLocalTasks = tasks.value.filter(
      t => (t.status === 'pending' || t.status === 'running') && !serverIds.has(t.id) && typeof t.id === 'number'
    )
    if (staleLocalTasks.length === 1) {
      const t = staleLocalTasks[0]
      try {
        const fresh = await apiGet<any>(`/api/tasks/${t.id}`, { timeout: 5000 })
        const wasActive = t.status === 'pending' || t.status === 'running'
        Object.assign(t, fresh)
        if (wasActive && (fresh.status === 'completed' || fresh.status === 'failed')) {
          t._doneAt = Date.now()
          _fireCallbacks(fresh)
          _scheduleAutoDismiss(t.id)
        }
      } catch { /* 单个查询失败不影响整体 */ }
    } else if (staleLocalTasks.length > 1) {
      try {
        const freshList = await apiPost<any[]>('/api/tasks/batch', {
          ids: staleLocalTasks.map(t => t.id),
        }, { timeout: 8000 })
        const freshMap = new Map((freshList || []).map((f: any) => [f.id, f]))
        for (const t of staleLocalTasks) {
          const fresh = freshMap.get(t.id)
          if (!fresh) continue
          const wasActive = t.status === 'pending' || t.status === 'running'
          Object.assign(t, fresh)
          if (wasActive && (fresh.status === 'completed' || fresh.status === 'failed')) {
            t._doneAt = Date.now()
            _fireCallbacks(fresh)
            _scheduleAutoDismiss(t.id)
          }
        }
      } catch { /* 批量查询失败不影响整体 */ }
    }

    tasks.value = tasks.value.filter(t => !t._dismissed)
  } catch (e) {
    // 静默失败（如未登录）
  }
}

async function pollLegacy() {
  if (!legacyTaskId.value && !legacyTaskStatus.value) return
  if (!legacyTaskId.value && legacyTaskStatus.value) return
  try {
    const res = await apiGet<any>(`/api/projects/init-task/${legacyTaskId.value}/status`)
    const wasActive = legacyTaskStatus.value?.status === 'pending' || legacyTaskStatus.value?.status === 'running'
    legacyTaskStatus.value = res
    if (import.meta.client) {
      localStorage.setItem('moyu_init_task', JSON.stringify({ id: legacyTaskId.value, ...res }))
    }
    if (res.status === 'completed') {
      const lid = legacyTaskId.value
      legacyTaskId.value = null
      _fireCallbacks({ task_type: 'init', id: `legacy-${lid}` })
      if (import.meta.client) {
        setTimeout(() => {
          const saved = localStorage.getItem('moyu_init_task')
          if (saved) {
            try {
              const p = JSON.parse(saved)
              if (p.status === 'completed') {
                const doneAt = new Date(p.created_at || Date.now()).getTime()
                if (Date.now() - doneAt > 24 * 60 * 60 * 1000) {
                  localStorage.removeItem('moyu_init_task')
                  legacyTaskStatus.value = null
                }
              }
            } catch {}
          }
        }, 30000)
      }
    } else if (res.status === 'failed') {
      legacyTaskId.value = null
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
  const hasActive = tasks.value.some(t => t.status === 'pending' || t.status === 'running')
  const hasLegacyActive = legacyTaskId.value || (legacyTaskStatus.value && (legacyTaskStatus.value.status === 'pending' || legacyTaskStatus.value.status === 'running'))
  if (!hasActive && !hasLegacyActive) {
    stopPolling()
  }
}

function startPolling() {
  if (pollTimer) return
  poll()
  pollTimer = setInterval(poll, 1500)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

// ===== 模块级 WebSocket =====

function getWsUrl(): string {
  const apiBase = (import.meta as any).client
    ? useRuntimeConfig().public.apiBase
    : 'http://localhost:8000'
  const url = new URL(apiBase)
  const wsProtocol = url.protocol === 'https:' ? 'wss' : 'ws'
  const token = localStorage.getItem('moyu_token') || ''
  return `${wsProtocol}://${url.host}/ws/tasks?token=${encodeURIComponent(token)}`
}

function connectWs() {
  if (!import.meta.client) return
  if (ws && ws.readyState === WebSocket.OPEN) return
  try {
    ws = new WebSocket(getWsUrl())
    ws.onopen = () => {
      if (pollTimer) {
        clearInterval(pollTimer)
        pollTimer = null
      }
    }
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'ping') {
          ws?.send(JSON.stringify({ type: 'pong' }))
          return
        }
        if (msg.type === 'task_update' && msg.task) {
          _applyWsUpdate(msg.task)
        }
      } catch {}
    }
    ws.onclose = () => {
      ws = null
      if (!pollTimer) startPolling()
      if (!wsReconnectTimer) {
        wsReconnectTimer = setTimeout(() => {
          wsReconnectTimer = null
          connectWs()
        }, WS_RECONNECT_DELAY)
      }
    }
    ws.onerror = () => {
      ws?.close()
    }
  } catch {
    // ws 连接失败，依赖 HTTP 轮询
  }
}

// ===== 自动清理超时 =====
const AUTO_DISMISS_MS = 24 * 60 * 60 * 1000

// ===== Composable =====

export function useBackgroundTasks() {
  if (import.meta.client && !polling) loadLegacyFromStorage()

  // 页面可见性变化时管理 WebSocket（仅注册一次）
  if (import.meta.client && !wsVisibilityRegistered) {
    wsVisibilityRegistered = true
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        connectWs()
        refreshTasks()
      } else {
        if (ws) { ws.close(); ws = null }
        if (wsReconnectTimer) { clearTimeout(wsReconnectTimer); wsReconnectTimer = null }
      }
    }
    document.addEventListener('visibilitychange', handleVisibility)
    connectWs()
    refreshTasks()
  }

  // 注册任务完成回调（taskType 支持前缀匹配，如 'chapter' 匹配 'chapter_generate'）
  function onTaskCompleted(taskType: string, callback: () => void) {
    if (!completionCallbacks.has(taskType)) {
      completionCallbacks.set(taskType, [])
    }
    completionCallbacks.get(taskType)!.push(callback)
  }

  // ===== 通用任务（新队列）=====
  function trackTask(task: any) {
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

  // ===== 旧 init-task（向下兼容）=====
  function startLegacy(id: number) {
    legacyTaskId.value = id
    legacyTaskStatus.value = { status: 'pending', progress: 0, status_message: '排队中...' }
    if (import.meta.client) localStorage.setItem('moyu_init_task', JSON.stringify({ id }))
    startPolling()
  }

  async function cancelTask(id: number | string) {
    try {
      if (typeof id === 'string' && id.startsWith('legacy-')) {
        const numericId = parseInt(id.replace('legacy-', ''))
        await apiPost(`/api/projects/init-task/${numericId}/cancel`, {})
      } else {
        await apiPost(`/api/tasks/${id}/cancel`, {})
      }
      const t = tasks.value.find(t => t.id === id)
      if (t) { t.status = 'cancelled'; t._doneAt = Date.now() }
      if (legacyTaskStatus.value) {
        legacyTaskStatus.value = { ...legacyTaskStatus.value, status: 'cancelled', status_message: '任务已取消' }
      }
    } catch (e) {
      console.warn('取消失败', e)
    }
  }

  async function dismissTask(id: number | string) {
    const t = tasks.value.find(t => t.id === id)
    if (t) t._dismissed = true
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

  function clearDoneTasks() {
    tasks.value = tasks.value.filter(t =>
      t.status === 'pending' || t.status === 'running'
    )
    if (legacyTaskStatus.value?.status === 'completed' ||
        legacyTaskStatus.value?.status === 'failed' ||
        legacyTaskStatus.value?.status === 'cancelled') {
      if (import.meta.client) localStorage.removeItem('moyu_init_task')
      legacyTaskStatus.value = null
      legacyTaskId.value = null
    }
  }

  // 刷新页面后恢复（仅客户端）
  if (import.meta.client && !pollTimer) {
    if (legacyTaskId.value) startPolling()
    else refreshTasks().then(() => { if (tasks.value.length || legacyTaskStatus.value) startPolling() })
  }

  // 合并展示列表（通用 + 旧 init-task）
  const allTasks = computed(() => {
    const list = tasks.value.map(t => ({
      ...t,
      _isLegacy: false,
      _steps: t.progress_details?.steps || null,
    }))
    if (legacyTaskId.value || legacyTaskStatus.value) {
      const lid = legacyTaskId.value || legacyTaskStatus.value?.id || 0
      list.push({
        id: `legacy-${lid}`,
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
          { label: '角色', done: legacyTaskStatus.value?.characters_done },
          { label: '地点', done: legacyTaskStatus.value?.locations_done },
          { label: '物品', done: legacyTaskStatus.value?.items_done },
          { label: '组织', done: legacyTaskStatus.value?.org_done },
          { label: '关系', done: legacyTaskStatus.value?.relations_done },
          { label: '大纲', done: legacyTaskStatus.value?.outline_done },
          { label: '验证补全', done: legacyTaskStatus.value?.validate_done },
        ],
        _failedStep: legacyTaskStatus.value?.failed_step || '',
        _taskId: lid,
      })
    }
    return list
  })

  const isActive = computed(() =>
    legacyTaskId.value !== null ||
    allTasks.value.some(t => t.status === 'pending' || t.status === 'running'),
  )

  const hasAnyTasks = computed(() =>
    allTasks.value.length > 0 ||
    (legacyTaskStatus.value && (legacyTaskStatus.value.status === 'failed'))
  )

  return {
    tasks: allTasks,
    isActive,
    hasAnyTasks,
    trackTask,
    startLegacy,
    refreshTasks,
    cancelTask,
    dismissTask,
    clearDoneTasks,
    onTaskCompleted,
    stopPolling,
    taskId: legacyTaskId,
    taskStatus: legacyTaskStatus,
    message: computed(() => legacyTaskStatus.value?.status_message || ''),
    progress: computed(() => legacyTaskStatus.value?.progress || 0),
    start: startLegacy,
  }
}
