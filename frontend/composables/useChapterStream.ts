// 章节编辑器辅助：写作风格 / Skill / 模型加载
import { apiGet } from './useApi'

/** 获取写作风格列表 */
export async function fetchWritingStyles(): Promise<any[]> {
  const res = await apiGet<any[]>('/api/writing-styles')
  return Array.isArray(res) ? res : []
}

/** 获取 Skill 列表 */
export async function fetchSkills(): Promise<any[]> {
  const res = await apiGet<any[]>('/api/skills')
  return Array.isArray(res) ? res : []
}

/** 获取可用 AI 模型列表 */
export async function fetchRemoteModels(): Promise<Array<{ value: string; label: string }>> {
  try {
    const res = await apiGet<any>('/api/ai-models/default/remote-models')
    if (res?.models) {
      return res.models.map((m: any) => ({ value: m.id, label: m.id }))
    }
  } catch {}
  return []
}
