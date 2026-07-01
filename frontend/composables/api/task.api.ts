/** 任务管理 API */
import { get, post, pid } from './client'
const P = (id?: number) => id || pid()
export const taskApi = {
  getActiveTasks: () => get('/tasks/active'),
  getStatus: (taskId: number) => get(`/tasks/${taskId}`),
  list: (params?: { taskType?: string; projectId?: number; status?: string; limit?: number }) => {
    const q = new URLSearchParams()
    if (params?.taskType) q.set('task_type', params.taskType)
    if (params?.projectId) q.set('project_id', String(params.projectId))
    if (params?.status) q.set('status', params.status)
    if (params?.limit) q.set('limit', String(params.limit))
    return get(`/tasks?${q.toString()}`)
  },
  getBatchStatus: (taskId: number, id?: number) => get(`/projects/${P(id)}/batch-generate/${taskId}/status`),
  getActiveBatch: (id?: number) => get(`/projects/${P(id)}/batch-generate/active`),
  cancelBatch: (taskId: number, id?: number) => post(`/projects/${P(id)}/batch-generate/${taskId}/cancel`),
  retryBatch: (taskId: number, id?: number) => post(`/projects/${P(id)}/batch-generate/${taskId}/retry`),
}
