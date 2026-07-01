/** 角色 API */
import { get, post, put, del, pid } from './client'
const P = (id?: number) => id || pid()

export const characterApi = {
  list: (id?: number) => get(`/projects/${P(id)}/characters`),
  create: (body: any, id?: number) => post(`/projects/${P(id)}/characters`, body),
  update: (characterId: number, body: any, id?: number) => put(`/projects/${P(id)}/characters/${characterId}`, body),
  delete: (characterId: number, id?: number) => del(`/projects/${P(id)}/characters/${characterId}`),
  generate: (id?: number) => post(`/projects/${P(id)}/characters/generate`),
  generateAsync: (body: { count: number; requirements?: string }, id?: number) => post(`/projects/${P(id)}/characters/generate-async`, body),
  batchGenerate: (body: any, id?: number) => post(`/projects/${P(id)}/characters/batch-generate-async`, body),
  getOrganizations: (characterId: number, id?: number) => get(`/projects/${P(id)}/characters/${characterId}/organizations`),
  // 职业
  getCareers: (characterId: number, id?: number) => get(`/projects/${P(id)}/characters/${characterId}/careers`),
  createCareer: (characterId: number, body: any, id?: number) => post(`/projects/${P(id)}/characters/${characterId}/careers`, body),
  updateCareer: (ccId: number, body: any, id?: number) => put(`/projects/${P(id)}/character-careers/${ccId}`, body),
  deleteCareer: (ccId: number, id?: number) => del(`/projects/${P(id)}/character-careers/${ccId}`),
  autoAssignCareers: (id?: number) => post(`/projects/${P(id)}/careers/auto-assign`),
  getChangeLogs: (characterId: number, id?: number) => get(`/projects/${P(id)}/characters/${characterId}/change-logs`),
  createChangeLog: (characterId: number, body: any, id?: number) => post(`/projects/${P(id)}/characters/${characterId}/change-logs`, body),
  deleteChangeLog: (characterId: number, logId: number, id?: number) => del(`/projects/${P(id)}/characters/${characterId}/change-logs/${logId}`),
}

// (charCareerApi moved to separate file)
