/** 世界观 API */
import { get, post, put, del, pid } from './client'
const P = (id?: number) => id || pid()
export const worldApi = {
  list: (id?: number) => get(`/projects/${P(id)}/worldview`),
  create: (body: any, id?: number) => post(`/projects/${P(id)}/worldview`, body),
  update: (worldId: number, body: any, id?: number) => put(`/projects/${P(id)}/worldview/${worldId}`, body),
  delete: (worldId: number, id?: number) => del(`/projects/${P(id)}/worldview/${worldId}`),
  getCore: (id?: number) => get(`/projects/${P(id)}/worldview/core`),
  generate: (body: any, id?: number) => post(`/projects/${P(id)}/worldview/generate`, body),
  generateCore: (body: any, id?: number) => post(`/projects/${P(id)}/worldview/generate-core`, body),
  updateCore: (body: any, id?: number) => put(`/projects/${P(id)}/worldview/core`, body),
  reindexVectors: (id?: number) => post(`/projects/${P(id)}/worldview/reindex`),
}
