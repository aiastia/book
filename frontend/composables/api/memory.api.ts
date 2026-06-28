/** 记忆 API */
import { get, post, put, del, pid } from './client'
const P = (id?: number) => id || pid()
export const memoryApi = {
  list: (id?: number) => get(`/projects/${P(id)}/memories`),
  create: (body: any, id?: number) => post(`/projects/${P(id)}/memories`, body),
  update: (memId: number, body: any, id?: number) => put(`/projects/${P(id)}/memories/${memId}`, body),
  delete: (memId: number, id?: number) => del(`/projects/${P(id)}/memories/${memId}`),
  clear: (id?: number) => post(`/projects/${P(id)}/memories/clear`),
  search: (query: string, id?: number) => get(`/projects/${P(id)}/memories/search?q=${encodeURIComponent(query)}`),
  getStats: (id?: number) => get(`/projects/${P(id)}/memories/stats`),
  reindex: (id?: number) => post(`/projects/${P(id)}/memories/reindex`),
}
