/** 章节 API */
import { get, post, put, del, pid, postSSE } from './client'
const P = (id?: number) => id || pid()

export const chapterApi = {
  list: (id?: number) => get(`/projects/${P(id)}/chapters`),
  get: (chapterId: number, id?: number) => get(`/projects/${P(id)}/chapters/${chapterId}`),
  create: (body: { chapter_number: number; title: string; outline_id?: number }, id?: number) =>
    post(`/projects/${P(id)}/chapters`, body),
  update: (chapterId: number, body: any, id?: number) =>
    put(`/projects/${P(id)}/chapters/${chapterId}`, body),
  delete: (chapterId: number, id?: number) => del(`/projects/${P(id)}/chapters/${chapterId}`),
  clear: (chapterId: number, cascade = false, id?: number) =>
    post(`/projects/${P(id)}/chapters/${chapterId}/clear?cascade=${cascade}`),

  /** 同步生成 */
  generate: (chapterId: number, id?: number) =>
    post(`/projects/${P(id)}/chapters/${chapterId}/generate`),
  /** 异步生成（单章）*/
  generateAsync: (chapterId: number, opts?: { skillName?: string; style?: any; narrativePov?: string; targetWords?: number; model?: string; thinkingMode?: string }, id?: number) => {
    const body: Record<string, any> = {}
    if (opts?.skillName) body.skill_name = opts.skillName
    if (opts?.style) {
      if (opts.style.config) body.style_config = opts.style.config
      if (opts.style.name) body.style_name = opts.style.name
      if (opts.style.custom_prompt) body.style_custom_prompt = opts.style.custom_prompt
      if (opts.style.style_traits) body.style_traits = opts.style.style_traits
    }
    if (opts?.narrativePov) body.narrative_pov = opts.narrativePov
    if (opts?.targetWords) body.target_word_count = opts.targetWords
    if (opts?.model) body.model = opts.model
    if (opts?.thinkingMode) body.thinking_mode = opts.thinkingMode
    return post(`/projects/${P(id)}/chapters/${chapterId}/generate-async`, body)
  },
  /** 批量生成 */
  batchGenerate: (id: number, opts: {
    chapterIds?: number[]; start?: number; count?: number
    targetWords?: number; modelOverride?: string; styleId?: number
    narrativePerspective?: string; enableAnalysis?: boolean
  } = {}) => {
    const body: Record<string, any> = { target_word_count: opts.targetWords || 2500, enable_analysis: opts.enableAnalysis ?? true, max_retries: 2 }
    if (opts.chapterIds) body.chapter_ids = opts.chapterIds
    else if (opts.start && opts.count) { body.start_chapter_number = opts.start; body.count = opts.count }
    if (opts.modelOverride) body.model_override = opts.modelOverride
    if (opts.styleId) body.style_id = opts.styleId
    if (opts.narrativePerspective) body.narrative_perspective = opts.narrativePerspective
    return post(`/projects/${id}/chapters/batch-generate`, body)
  },
  /** 重写/润色（SSE 流式版，防 524 超时） */
  regenerate: (chapterId: number, body: string | Record<string, any>, id?: number, targetWords?: number) =>
    postSSE(`/projects/${P(id)}/chapters/${chapterId}/regenerate/stream`,
      typeof body === 'string' ? { instructions: body, target_word_count: targetWords } : body),
  getNavigation: (chapterId: number, id?: number) =>
    get(`/projects/${P(id)}/chapters/${chapterId}/navigation`),
  getAnnotations: (chapterId: number, id?: number) =>
    get(`/projects/${P(id)}/chapters/${chapterId}/annotations`),

  // 重写任务
  getRegenTasks: (chapterId: number, id?: number) =>
    get(`/projects/${P(id)}/chapters/${chapterId}/regeneration/tasks`),
  getRegenTaskDetail: (chapterId: number, taskId: number, id?: number) =>
    get(`/projects/${P(id)}/chapters/${chapterId}/regeneration/${taskId}`),
  applyRegenTask: (chapterId: number, taskId: number, id?: number) =>
    post(`/projects/${P(id)}/chapters/${chapterId}/regeneration/${taskId}/apply`),
  partialRegenerate: (chapterId: number, body: any, id?: number) =>
    postSSE(`/projects/${P(id)}/chapters/${chapterId}/partial-regenerate/stream`, body),
  applyPartialRegen: (chapterId: number, body: any, id?: number) =>
    post(`/projects/${P(id)}/chapters/${chapterId}/apply-partial-regenerate`, body),

  // 分析
  triggerAnalysis: (chapterId: number, id?: number) =>
    post(`/projects/${P(id)}/chapters/${chapterId}/analyze`),
  getAnalysisTaskStatus: (chapterId: number, id?: number) =>
    get(`/projects/${P(id)}/chapters/${chapterId}/analyze/status`),
  analyzeAll: (id?: number) => post(`/projects/${P(id)}/chapters/analyze-all`),
  cleanupAnalyses: (id?: number) => post(`/projects/${P(id)}/chapters/cleanup-duplicate-analyses`),
  syncForeshadows: (chapterIds?: number[], id?: number) =>
    post(`/projects/${P(id)}/chapters/sync-foreshadows`, { chapter_ids: chapterIds }),
  getAnalyses: (id?: number) => get(`/projects/${P(id)}/analyses`),
  getAnalysis: (chapterNumber: number, id?: number) =>
    get(`/projects/${P(id)}/analyses/${chapterNumber}`),

  // 去AI味（SSE 流式，防网关超时）
  aiDenoising: (body: { text: string }) => postSSE(`/projects/${P()}/ai-denoising/stream`, body),

  // 章节转语音（Director 分析 → SSML）
  tts: (chapterId: number, body?: { voice?: string; chunk_size?: number; model?: string }, id?: number) =>
    post(`/projects/${P(id)}/chapters/${chapterId}/tts`, body || {}),

  // 分镜剧本（Director → Screenwriter → 分镜 JSON）
  generateScreenplay: (chapterId: number, body?: { chunk_size?: number; model?: string }, id?: number) =>
    post(`/projects/${P(id)}/chapters/${chapterId}/screenplay`, body || {}),
  getScreenplay: (chapterId: number, id?: number) =>
    get(`/projects/${P(id)}/chapters/${chapterId}/screenplay`),
}
