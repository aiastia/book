/** 组织 API */
import { get, post, put, del, pid } from './client'
const P = (id?: number) => id || pid()
export const organizationApi = {
  list: (id?: number) => get(`/projects/${P(id)}/organizations`),
  create: (body: any, id?: number) => post(`/projects/${P(id)}/organizations`, body),
  update: (orgId: number, body: any, id?: number) => put(`/projects/${P(id)}/organizations/${orgId}`, body),
  delete: (orgId: number, id?: number) => del(`/projects/${P(id)}/organizations/${orgId}`),
  generate: (id?: number) => post(`/projects/${P(id)}/organizations/generate`),
  generateAsync: (body: any, id?: number) => post(`/projects/${P(id)}/organizations/generate-async`, body),
  getMembers: (orgId: number, id?: number) => get(`/projects/${P(id)}/organizations/${orgId}/members`),
  addMember: (orgId: number, body: any, id?: number) => post(`/projects/${P(id)}/organizations/${orgId}/members`, body),
  updateMember: (memberId: number, body: any, id?: number) => put(`/projects/${P(id)}/organization-members/${memberId}`, body),
  removeMember: (memberId: number, id?: number) => del(`/projects/${P(id)}/organization-members/${memberId}`),
  generateMembers: (orgId: number, body?: any, id?: number) => post(`/projects/${P(id)}/organizations/${orgId}/members/generate`),
  generateAllMembers: (id?: number) => post(`/projects/${P(id)}/organizations/members/generate-all`),
  getTree: (id?: number) => get(`/projects/${P(id)}/organizations/tree`),
  updateTree: (body: any, id?: number) => put(`/projects/${P(id)}/organizations/tree`, body),
  autoAnalyze: (id?: number) => post(`/projects/${P(id)}/organizations/auto-analyze`),
}
