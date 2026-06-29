/** 全局 API（不依赖 project_id） */
import { get, post, postSSE } from './client'

export const globalApi = {
  inspirationStep: (step: string, body: any) => post(`/projects/global-inspiration/step/${step}`, body),
  inspirationStepStream: (step: string, body: any) => postSSE(`/projects/global-inspiration/step/${step}/stream`, body),
  inspirationQuickComplete: (body: any) => post('/projects/global-inspiration/quick-complete', body),
  getStats: () => get('/stats'),
  getRecentEdits: () => get('/recent-edits'),
  listWritingStyles: () => get('/writing-styles'),
}
