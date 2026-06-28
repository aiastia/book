/** 地点 API */
import { get, post, put, del, pid } from './client'
const P = (id?: number) => id || pid()
export const locationApi = {
  list: (id?: number) => get(`/projects/${P(id)}/locations`),
  create: (body: any, id?: number) => post(`/projects/${P(id)}/locations`, body),
  update: (locId: number, body: any, id?: number) => put(`/projects/${P(id)}/locations/${locId}`, body),
  delete: (locId: number, id?: number) => del(`/projects/${P(id)}/locations/${locId}`),
  generate: (body: any = {}, id?: number) => post(`/projects/${P(id)}/locations/generate`),
  getTree: (id?: number) => get(`/projects/${P(id)}/locations/tree`),
}
