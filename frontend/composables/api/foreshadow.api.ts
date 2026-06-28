/** 伏笔 API */
import { get, post, put, del, pid } from './client'
const P = (id?: number) => id || pid()
export const foreshadowApi = {
  list: (status?: string, id?: number) => get(`/projects/${P(id)}/foreshadows${status ? `?status=${status}` : ''}`),
  create: (body: any, id?: number) => post(`/projects/${P(id)}/foreshadows`, body),
  update: (fid: number, body: any, id?: number) => put(`/projects/${P(id)}/foreshadows/${fid}`, body),
  delete: (fid: number, id?: number) => del(`/projects/${P(id)}/foreshadows/${fid}`),
  batchDelete: (ids: number[], id?: number) => post(`/projects/${P(id)}/foreshadows/batch-delete`, { ids }),
  plan: (id?: number) => post(`/projects/${P(id)}/foreshadows/plan`),
  plant: (fid: number, chapterNumber: number, hintText = '', id?: number) =>
    post(`/projects/${P(id)}/foreshadows/${fid}/plant`, { chapter_number: chapterNumber, hint_text: hintText }),
  resolve: (fid: number, chapterNumber: number, resolutionText = '', isPartial = false, id?: number) =>
    post(`/projects/${P(id)}/foreshadows/${fid}/resolve`, { chapter_number: chapterNumber, resolution_text: resolutionText, is_partial: isPartial }),
  abandon: (fid: number, reason = '', id?: number) => post(`/projects/${P(id)}/foreshadows/${fid}/abandon`, { reason }),
  getPendingResolve: (currentChapter: number, id?: number) => get(`/projects/${P(id)}/foreshadows/pending-resolve?chapter=${currentChapter}`),
  getOverdue: (currentChapter: number, id?: number) => get(`/projects/${P(id)}/foreshadows/overdue?chapter=${currentChapter}`),
}
