/** 提示词模板 API */
import { get, post, del } from './client'
export const promptApi = {
  list: () => get('/prompt-templates'),
  get: (id: number) => get(`/prompt-templates/${id}`),
  create: (body: any) => post('/prompt-templates', body),
  delete: (id: number) => del(`/prompt-templates/${id}`),
  listVersions: (templateId: number) => get(`/prompt-templates/${templateId}/versions`),
  createVersion: (templateId: number, body: any) => post(`/prompt-templates/${templateId}/versions`, body),
  activateVersion: (templateId: number, versionId: number) =>
    post(`/prompt-templates/${templateId}/versions/${versionId}/activate`),
}
