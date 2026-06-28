/** 全局 API（不依赖 project_id） */
import { get, post } from './client'
export const globalApi = {
  inspirationStep: (step: string, body: any) => post(`/global-inspiration/step/${step}`, body),
  inspirationQuickComplete: (body: any) => post('/global-inspiration/quick-complete', body),
  getStats: () => get('/stats'),
  getRecentEdits: () => get('/recent-edits'),
  listWritingStyles: () => get('/writing-styles'),
}
