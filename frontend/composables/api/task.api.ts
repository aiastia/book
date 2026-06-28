/** 任务管理 API */
import { get, post, pid } from './client'
const P = (id?: number) => id || pid()
export const taskApi = {
  getActiveTasks: () => get('/tasks/active'),
  getStatus: (taskId: number) => get(`/tasks/${taskId}`),
  getBatchStatus: (taskId: number, id?: number) => get(`/projects/${P(id)}/batch-generate/${taskId}/status`),
  getActiveBatch: (id?: number) => get(`/projects/${P(id)}/batch-generate/active`),
  cancelBatch: (taskId: number, id?: number) => post(`/projects/${P(id)}/batch-generate/${taskId}/cancel`),
  retryBatch: (taskId: number, id?: number) => post(`/projects/${P(id)}/batch-generate/${taskId}/retry`),
}
