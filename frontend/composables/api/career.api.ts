import { get, post, put, del } from './client'
import { pid } from './client'
const P = (id?: number) => id || pid()
export const careerApi = {
  list: (id?: number) => get(`/projects/${P(id)}/careers`),
  create: (body: any, id?: number) => post(`/projects/${P(id)}/careers`, body),
  update: (careerId: number, body: any, id?: number) => put(`/projects/${P(id)}/careers/${careerId}`, body),
  delete: (careerId: number, id?: number) => del(`/projects/${P(id)}/careers/${careerId}`),
  generate: (body: any = {}, id?: number) => post(`/projects/${P(id)}/careers/generate`),
  autoAssign: (id?: number) => post(`/projects/${P(id)}/careers/auto-assign`),
}
