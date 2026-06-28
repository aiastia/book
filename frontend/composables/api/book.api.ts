/** 书（项目）API */
import { get, post, put, del, pid } from './client'
const P = (id?: number) => id || pid()

export const bookApi = {
  list: () => get('/books'),
  create: (title: string, genre = '', synopsis = '', outlineMode = 'one_to_one') =>
    post('/books', { title, genre, synopsis, outline_mode: outlineMode }),
  get: (id?: number) => get(`/projects/${P(id)}`),
  update: (body: any, id?: number) => put(`/projects/${P(id)}`, body),
  delete: (id: number) => del(`/projects/${id}`),
  import: (data: any) => post('/projects/import', data),
  export: (id?: number) => get(`/projects/${P(id)}/export?format=json`),
  getStats: () => get('/stats'),
  getRecentEdits: () => get('/recent-edits'),
  getThinkingModes: (id?: number) => get(`/projects/${P(id)}/thinking-modes`),
  saveThinkingModes: (modes: Record<string, any>, id?: number) =>
    put(`/projects/${P(id)}/thinking-modes`, { modes }),
  // 灵感
  inspirationStep: (step: string, body: any, id?: number) =>
    post(`/projects/${P(id)}/inspiration/step/${step}`, body),
  inspirationQuickComplete: (body: any, id?: number) =>
    post(`/projects/${P(id)}/inspiration/quick-complete`, body),
}
