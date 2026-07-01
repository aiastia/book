/** 世界观 API */
import { get, post, put, del, pid } from './client'
const P = (id?: number) => id || pid()
export const worldApi = {
  list: (id?: number) => get(`/projects/${P(id)}/worlds`),
  create: (body: any, id?: number) => post(`/projects/${P(id)}/worlds`, body),
  update: (worldId: number, body: any, id?: number) => put(`/projects/${P(id)}/worlds/${worldId}`, body),
  delete: (worldId: number, id?: number) => del(`/projects/${P(id)}/worlds/${worldId}`),
  getCore: (id?: number) => get(`/projects/${P(id)}/world-core`),
  generate: (body: any, id?: number) => post(`/projects/${P(id)}/worlds/generate`, body),
  generateCore: (body: any, id?: number) => post(`/projects/${P(id)}/world-core/generate-async`, body),
  updateCore: (body: any, id?: number) => put(`/projects/${P(id)}/world-core`, body),
  reindexVectors: (id?: number) => post(`/projects/${P(id)}/worlds/reindex-vectors`),
}
