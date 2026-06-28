/** 角色-职业关联 API */
import { get, post, pid } from './client'
const P = (id?: number) => id || pid()
export const charCareerApi = {
  list: (id?: number) => get(`/projects/${P(id)}/character-careers`),
  create: (body: any, id?: number) => post(`/projects/${P(id)}/character-careers`, body),
}
