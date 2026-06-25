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

// 任务完成回调注册表：{ taskTypePrefix: callback[] }
const completionCallbacks = new Map<string, Array<() => void>>()
// 记录已触发过的 task id，避免重复回调
const triggeredIds = new Set<string | number>()

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

  // ===== WebSocket 连接管理 =====
  let ws: WebSocket | null = null
  let wsReconnectTimer: any = null
  let wsHeartbeatTimer: any = null
  const WS_RECONNECT_DELAY = 5000

  function getWsUrl(): string {
    // 检测当前页面协议和 API host
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
        // WebSocket 连接成功，停止 HTTP 轮询
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
        // 断开后回退到 HTTP 轮询
        if (!pollTimer) startPolling()
        // 延迟重连
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

  function _applyWsUpdate(taskData: any) {
    // 通过 WS 推送更新本地任务状态
    const existing = tasks.value.find(t => t.id === taskData.id)
    if (existing) {
      const wasActive = existing.status === 'pending' || existing.status === 'running'
      Object.assign(existing, taskData)
      if (wasActive && (taskData.status === 'completed' || taskData.status === 'failed')) {
        existing._doneAt = Date.now()
        _fireCallbacks(taskData)
      }
    } else {
      tasks.value.push({ ...taskData, _source: 'generic' })
    }
  }

  // 页面可见性变化时管理 WebSocket
  if (import.meta.client) {
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        connectWs()
      } else {
        // 页面隐藏时关闭 WebSocket（节省资源）
        if (ws) { ws.close(); ws = null }
        if (wsReconnectTimer) { clearTimeout(wsReconnectTimer); wsReconnectTimer = null }
      }
    }
    document.addEventListener('visibilitychange', handleVisibility)
    // 初始连接
    connectWs()
  }

  // 注册任务完成回调（taskType 支持前缀匹配，如 'chapter' 匹配 'chapter_generate'）
  function onTaskCompleted(taskType: string, callback: () => void) {
    if (!completionCallbacks.has(taskType)) {
      completionCallbacks.set(taskType, [])
    }
    completionCallbacks.get(taskType)!.push(callback)
  }

  // 触发匹配的回调
  function _fireCallbacks(task: any) {
    const ttype = task.task_type || ''
    const tid = task.id
    if (triggeredIds.has(tid)) return
    triggeredIds.add(tid)
    // 收集所有匹配的回调（避免遍历时修改 Map）
    const cbs: Array<() => void> = []
    for (const [prefix, callbacks] of completionCallbacks.entries()) {
      if (ttype.startsWith(prefix)) {
        cbs.push(...callbacks)
      }
    }
    // 异步触发，避免在 watch 中同步执行
    if (cbs.length) {
      nextTick(() => cbs.forEach(cb => { try { cb() } catch {} }))
    }
  }

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
      const serverIds = new Set(list.map((t: any) => t.id))

      // 合并服务端最新状态
      for (const st of list) {
        const existing = tasks.value.find(t => t.id === st.id)
        if (existing) {
          // 检测状态变更：running/pending → completed
          const wasActive = existing.status === 'pending' || existing.status === 'running'
          const isDone = st.status === 'completed'
          Object.assign(existing, st)
          if (wasActive && isDone) {
            _fireCallbacks(st)
          }
        } else {
          tasks.value.push({ ...st, _source: 'generic' })
        }
      }

      // 手动清理：已完成超过 24 小时的任务自动移除
      const now = Date.now()
      const dayAgo = now - 24 * 60 * 60 * 1000
      tasks.value = tasks.value.filter(t => {
        if (t._dismissed) return false  // 被用户主动关闭的，立刻移除
        // 已完成/失败/取消的任务，保留 24 小时
        if (t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled') {
          if (!t._doneAt) t._doneAt = now
          if (t._doneAt < dayAgo) return false
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
        // 触发 init task 完成回调
        _fireCallbacks({ task_type: 'init', id: `legacy-${lid}` })
        // 不再自动清除 legacyTaskStatus，保留 24 小时展示
        if (import.meta.client) {
          // 延迟清除 localStorage（24h 后由 refreshTasks 移除）
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
        // 失败后保留状态，停止轮询该任务但不清除
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
    // 仅在所有任务都被手动关闭后才停止轮询
    // (不再因任务完成而自动停止)
    if (!legacyTaskId.value && tasks.value.length === 0 && !legacyTaskStatus.value) {
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
      if (t) { t.status = 'cancelled'; t._doneAt = Date.now() }
      // 同时更新 legacy task status
      if (legacyTaskStatus.value) {
        legacyTaskStatus.value = { ...legacyTaskStatus.value, status: 'cancelled', status_message: '任务已取消' }
      }
    } catch (e) {
      console.warn('取消失败', e)
    }
  }

  async function dismissTask(id: number | string) {
    // 标记为已关闭（在下次 refreshTasks 时过滤掉）
    const t = tasks.value.find(t => t.id === id)
    if (t) t._dismissed = true
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

  // 清空所有已完成/失败/取消的任务
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

  // 是否有任何任务显示（包括已完成待关闭的）
  const hasAnyTasks = computed(() =>
    allTasks.value.length > 0 ||
    (legacyTaskStatus.value && (legacyTaskStatus.value.status === 'failed'))
  )

  return {
    tasks: allTasks,
    isActive,
    hasAnyTasks,
    trackTask,
    startLegacy,    // 向下兼容：旧代码调 start(id)
    cancelTask,
    dismissTask,
    clearDoneTasks,
    onTaskCompleted,
    stopPolling,
    // 向下兼容旧 useInitTask 的返回
    taskId: legacyTaskId,
    taskStatus: legacyTaskStatus,
    message: computed(() => legacyTaskStatus.value?.status_message || ''),
    progress: computed(() => legacyTaskStatus.value?.progress || 0),
    start: startLegacy,
  }
}
