/** 大纲 API */
import { get, post, put, del, pid } from './client'
const P = (id?: number) => id || pid()

export const outlineApi = {
  list: (id?: number) => get(`/projects/${P(id)}/outlines`),
  create: (body: any, id?: number) => post(`/projects/${P(id)}/outlines`, body),
  update: (outlineId: number, body: any, id?: number) => put(`/projects/${P(id)}/outlines/${outlineId}`, body),
  delete: (outlineId: number, id?: number) => del(`/projects/${P(id)}/outlines/${outlineId}`),
  generate: (id: number, opts: { chapterCount?: number; narrativePov?: string; aiModel?: string } = {}) =>
    post(`/projects/${id}/outlines/generate-async`, { chapter_count: opts.chapterCount || 10, narrative_pov: opts.narrativePov || '', ai_model: opts.aiModel || '' }),
  continue: (id: number, body: any = {}) => post(`/projects/${id}/outlines/continue-async`, body),
  expand: (outlineId: number, targetCount: number, mode = 'new', id?: number) =>
    post(`/projects/${P(id)}/outlines/${outlineId}/expand-async`, { target_chapter_count: targetCount, mode }),
  batchExpand: (targetCount: number, id?: number) =>
    post(`/projects/${P(id)}/outlines/batch-expand-async`, { target_chapter_count: targetCount }),
  getChapters: (outlineId: number, id?: number) => get(`/projects/${P(id)}/outlines/${outlineId}/chapters`),
  deleteChapters: (outlineId: number, id?: number) => del(`/projects/${P(id)}/outlines/${outlineId}/chapters`),
  getPendingEntities: (id?: number) => get(`/projects/${P(id)}/outlines/pending-entities`),
  generatePendingEntities: (id?: number) => post(`/projects/${P(id)}/outlines/generate-pending-entities`),
}
