/** 关系 API */
import { get, post, put, del, pid } from './client'
const P = (id?: number) => id || pid()
export const relationApi = {
  list: (id?: number) => get(`/projects/${P(id)}/relations`),
  create: (body: any, id?: number) => post(`/projects/${P(id)}/relations`, body),
  update: (relId: number, body: any, id?: number) => put(`/projects/${P(id)}/relations/${relId}`, body),
  delete: (relId: number, id?: number) => del(`/projects/${P(id)}/relations/${relId}`),
  getGraph: (id?: number) => get(`/projects/${P(id)}/relations/graph`),
  autoRebuild: (id?: number) => post(`/projects/${P(id)}/relations/auto-rebuild`),
  getTypes: (id?: number) => get(`/projects/${P(id)}/relations/types`),
  renameType: (oldName: string, newName: string, id?: number) => put(`/projects/${P(id)}/relations/types/rename`, body),
  deleteType: (typeId: number, id?: number) => del(`/projects/${P(id)}/relations/types/${typeId}`),
  getChangeLogs: (relId: number, id?: number) => get(`/projects/${P(id)}/relations/${relId}/change-logs`),
  createChangeLog: (relId: number, body: any, id?: number) => post(`/projects/${P(id)}/relations/${relId}/change-logs`, body),
  deleteChangeLog: (relId: number, logId: number, id?: number) => del(`/projects/${P(id)}/relations/${relId}/change-logs/${logId}`),
}
