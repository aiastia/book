/** 物品 API */
import { get, post, put, del, pid } from './client'
const P = (id?: number) => id || pid()
export const itemApi = {
  list: (id?: number) => get(`/projects/${P(id)}/items`),
  create: (body: any, id?: number) => post(`/projects/${P(id)}/items`, body),
  update: (itemId: number, body: any, id?: number) => put(`/projects/${P(id)}/items/${itemId}`, body),
  delete: (itemId: number, id?: number) => del(`/projects/${P(id)}/items/${itemId}`),
  generate: (body: any = {}, id?: number) => post(`/projects/${P(id)}/items/generate`),
}
