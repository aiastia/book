import { get, post, put, del } from './client'
export const skillApi = {
  list: () => get('/skills'),
  create: (body: any) => post('/skills', body),
  update: (skillId: number, body: any) => put(`/skills/${skillId}`, body),
  deleteCustom: (skillId: number) => del(`/skills/${skillId}/custom`),
  reset: (skillId: number) => post(`/skills/${skillId}/reset`),
  resetAll: () => post('/skills/reset-all'),
  reload: () => post('/skills/reload'),
}
