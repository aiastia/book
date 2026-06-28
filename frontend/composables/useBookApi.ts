/**
 * 墨鱼写作系统 · 统一 API 客户端
 *
 * 所有后端接口集中在此，不再散落 apiGet/apiPost 裸调。
 * 好处：字段名统一、URL 一处管理、返回类型明确、可测试。
 *
 * 用法：
 *   const api = useBookApi()
 *   const books = await api.listBooks()
 *   await api.generateChapters(17, { start: 3, count: 5 })
 */
import { useRuntimeConfig, navigateTo } from '#imports'

// ===== 基础 HTTP（内部） =====
async function _fetch(path: string, opts: RequestInit = {}): Promise<any> {
  const config = useRuntimeConfig()
  const base = import.meta.client ? config.public.apiBase : 'http://localhost:8000'
  const url = `${base}/api${path}`

  // token 从 localStorage 读取（兼容现有认证体系）
  let token = ''
  if (import.meta.client) {
    token = localStorage.getItem('moyu_token') || ''
  }
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(opts.headers as Record<string, string> || {}),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(url, { ...opts, headers })
  if (res.status === 401) {
    // 401 → 重新登录 → 重试
    if (import.meta.client) {
      localStorage.removeItem('moyu_token')
      await navigateTo('/login')
    }
    throw new Error('认证已过期，请重新登录')
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail.detail || detail.message || `HTTP ${res.status}`)
  }
  if (res.headers.get('content-type')?.includes('application/json')) {
    return res.json()
  }
  return res.text()
}

export function useBookApi() {
  // ==================== 项目（书） ====================
  async function listBooks() {
    return _fetch('/books')
  }

  async function createBook(title: string, genre = '', synopsis = '', outlineMode = 'one_to_one') {
    return _fetch('/books', {
      method: 'POST',
      body: JSON.stringify({ title, genre, synopsis, outline_mode: outlineMode }),
    })
  }

  async function getProject(projectId?: number) {
    const pid = projectId || _pid()
    return _fetch(`/projects/${pid}`)
  }

  async function deleteProject(projectId: number) {
    return _fetch(`/projects/${projectId}`, { method: 'DELETE' })
  }

  // ==================== 章节 ====================

  /** 获取章节列表（不含正文内容，有 content_preview） */
  async function listChapters(projectId?: number) {
    const pid = projectId || _pid()
    return _fetch(`/projects/${pid}/chapters`)
  }

  /** 获取单章完整内容 */
  async function getChapter(chapterId: number, projectId?: number) {
    const pid = projectId || _pid()
    return _fetch(`/projects/${pid}/chapters/${chapterId}`)
  }

  /** 批量生成章节（异步） */
  async function generateChapters(
    projectId: number,
    opts: {
      chapterIds?: number[]
      start?: number
      count?: number
      targetWords?: number
      modelOverride?: string
      styleId?: number
      narrativePerspective?: string
      enableAnalysis?: boolean
    } = {},
  ) {
    const body: Record<string, any> = {
      target_word_count: opts.targetWords || 2500,
      enable_analysis: opts.enableAnalysis ?? true,
      max_retries: 2,
    }
    if (opts.chapterIds) {
      body.chapter_ids = opts.chapterIds
    } else if (opts.start && opts.count) {
      body.start_chapter_number = opts.start
      body.count = opts.count
    }
    if (opts.modelOverride) body.model_override = opts.modelOverride
    if (opts.styleId) body.style_id = opts.styleId
    if (opts.narrativePerspective) body.narrative_perspective = opts.narrativePerspective
    return _fetch(`/projects/${projectId}/chapters/batch-generate`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
  }

  /** 创建章节 */
  async function createChapter(
    projectId: number,
    chapterNumber: number,
    title: string,
  ) {
    return _fetch(`/projects/${projectId}/chapters`, {
      method: 'POST',
      body: JSON.stringify({ chapter_number: chapterNumber, title }),
    })
  }

  /** 清空章节 */
  async function clearChapter(chapterId: number, projectId?: number) {
    const pid = projectId || _pid()
    return _fetch(`/projects/${pid}/chapters/${chapterId}/clear`, { method: 'POST' })
  }

  /** 重写章节 */
  async function regenerateChapter(
    chapterId: number,
    instructions: string,
    projectId?: number,
    targetWords?: number,
  ) {
    const pid = projectId || _pid()
    return _fetch(`/projects/${pid}/chapters/${chapterId}/regenerate`, {
      method: 'POST',
      body: JSON.stringify({ instructions, target_word_count: targetWords }),
    })
  }

  // ==================== 大纲 ====================
  async function listOutlines(projectId?: number) {
    const pid = projectId || _pid()
    return _fetch(`/projects/${pid}/outlines`)
  }

  /** 生成大纲（异步） */
  async function generateOutline(projectId: number, chapterCount = 10) {
    return _fetch(`/projects/${projectId}/outlines/generate-async`, {
      method: 'POST',
      body: JSON.stringify({ chapter_count: chapterCount }),
    })
  }

  /** 续写大纲 */
  async function continueOutline(projectId: number, opts: Record<string, any> = {}) {
    return _fetch(`/projects/${projectId}/outlines/continue-async`, {
      method: 'POST',
      body: JSON.stringify(opts),
    })
  }

  /** 展开大纲（1-N）*/
  async function expandOutline(
    projectId: number,
    outlineId: number,
    targetChapterCount: number,
  ) {
    return _fetch(`/projects/${projectId}/outlines/${outlineId}/expand-async`, {
      method: 'POST',
      body: JSON.stringify({ target_chapter_count: targetChapterCount }),
    })
  }

  // ==================== 写作风格 ====================
  async function listWritingStyles() {
    return _fetch('/writing-styles')
  }

  // ==================== 通用任务 ====================
  async function getBatchStatus(taskId: number, projectId?: number) {
    const pid = projectId || _pid()
    return _fetch(`/projects/${pid}/batch-generate/${taskId}/status`)
  }

  async function getActiveBatchTask(projectId?: number) {
    const pid = projectId || _pid()
    return _fetch(`/projects/${pid}/batch-generate/active`)
  }

  async function cancelBatchTask(taskId: number, projectId?: number) {
    const pid = projectId || _pid()
    return _fetch(`/projects/${pid}/batch-generate/${taskId}/cancel`, { method: 'POST' })
  }

  async function retryBatchTask(taskId: number, projectId?: number) {
    const pid = projectId || _pid()
    return _fetch(`/projects/${pid}/batch-generate/${taskId}/retry`, { method: 'POST' })
  }

  // ==================== 角色 / 实体 ====================
  async function listCharacters(projectId?: number) {
    const pid = projectId || _pid()
    return _fetch(`/projects/${pid}/characters`)
  }

  async function listItems(projectId?: number) {
    const pid = projectId || _pid()
    return _fetch(`/projects/${pid}/items`)
  }

  async function listLocations(projectId?: number) {
    const pid = projectId || _pid()
    return _fetch(`/projects/${pid}/locations`)
  }

  // ==================== AI 模型 ====================
  async function listAiModels() {
    return _fetch('/ai-models')
  }

  async function testAiModel(modelId: number) {
    return _fetch(`/ai-models/${modelId}/test`, { method: 'POST' })
  }

  async function fetchDefaultRemoteModels() {
    return _fetch('/ai-models/default/remote-models')
  }

  // ==================== 封面 ====================
  async function generateCoverPrompt(projectId?: number) {
    const pid = projectId || _pid()
    return _fetch(`/projects/${pid}/cover/generate-prompt`, { method: 'POST' })
  }

  // ==================== 待补充实体 ====================
  async function getPendingEntities(projectId?: number) {
    const pid = projectId || _pid()
    return _fetch(`/projects/${pid}/outlines/pending-entities`)
  }

  async function generatePendingEntities(projectId?: number) {
    const pid = projectId || _pid()
    return _fetch(`/projects/${pid}/outlines/generate-pending-entities`, { method: 'POST' })
  }

  return {
    // 书
    listBooks,
    createBook,
    getProject,
    deleteProject,
    // 章节
    listChapters,
    getChapter,
    generateChapters,
    createChapter,
    clearChapter,
    regenerateChapter,
    // 大纲
    listOutlines,
    generateOutline,
    continueOutline,
    expandOutline,
    // 写作风格
    listWritingStyles,
    // 任务
    getBatchStatus,
    getActiveBatchTask,
    cancelBatchTask,
    retryBatchTask,
    // 实体
    listCharacters,
    listItems,
    listLocations,
    // AI
    listAiModels,
    testAiModel,
    fetchDefaultRemoteModels,
    // 封面
    generateCoverPrompt,
    // pending
    getPendingEntities,
    generatePendingEntities,
  }
}

/** 从 URL 或 useProject 获取当前 project_id */
function _pid(): number {
  // 尝试从 URL path /projects/{id}/... 解析
  if (import.meta.client) {
    const m = window.location.pathname.match(/\/projects\/(\d+)/)
    if (m) return Number(m[1])
  }
  return 0
}
