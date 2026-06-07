// 全局项目初始化任务状态：用户提交后可在任意页面查看进度。
// 任务ID 存 localStorage，刷新/切页后能恢复轮询。
import { apiGet } from './useApi'

const taskId = ref<number | null>(null)
const taskStatus = ref<any>(null)
let pollTimer: any = null

function loadFromStorage() {
  if (import.meta.client) {
    const saved = localStorage.getItem('moyu_init_task')
    if (saved) {
      const parsed = JSON.parse(saved)
      taskId.value = parsed.id
      // 已完成的不恢复轮询
      if (parsed.status === 'completed' || parsed.status === 'failed') {
        taskStatus.value = parsed
        taskId.value = null
      }
    }
  }
}

export function useInitTask() {
  if (import.meta.client && taskId.value === null && !pollTimer) loadFromStorage()

  function start(id: number) {
    taskId.value = id
    taskStatus.value = { status: 'pending', progress: 0, status_message: '排队中...' }
    if (import.meta.client) localStorage.setItem('moyu_init_task', JSON.stringify({ id }))
    startPolling()
  }

  async function poll() {
    if (!taskId.value) return
    try {
      const res = await apiGet<any>(`/api/projects/init-task/${taskId.value}/status`)
      taskStatus.value = res
      if (import.meta.client) {
        localStorage.setItem('moyu_init_task', JSON.stringify({ id: taskId.value, ...res }))
      }
      if (res.status === 'completed' || res.status === 'failed') {
        stopPolling()
        taskId.value = null
        if (import.meta.client) setTimeout(() => {
          localStorage.removeItem('moyu_init_task')
          taskStatus.value = null
        }, 10000) // 完成后 10 秒清除提示
      }
    } catch (e) {
      console.warn('轮询失败', e)
    }
  }

  function startPolling() {
    stopPolling()
    poll() // 立即查一次
    pollTimer = setInterval(poll, 3000) // 每 3 秒查一次
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  }

  // 恢复轮询（刷新/切页后，仅客户端）
  if (import.meta.client && taskId.value && !pollTimer && taskStatus.value?.status !== 'completed' && taskStatus.value?.status !== 'failed') {
    startPolling()
  }

  const isActive = computed(() => taskId.value !== null && taskStatus.value?.status !== 'completed' && taskStatus.value?.status !== 'failed')
  const progress = computed(() => taskStatus.value?.progress || 0)
  const message = computed(() => taskStatus.value?.status_message || '')

  return { taskId, taskStatus, isActive, progress, message, start, stopPolling }
}
