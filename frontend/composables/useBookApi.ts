/**
 * 墨鱼写作系统 · 统一 API 客户端
 *
 * 所有后端接口集中在此 Class，不再散落 apiGet/apiPost 裸调。
 * 好处：字段名统一（camelCase）、URL 一处管理、返回类型明确、可测试。
 *
 * 用法：
 *   const api = useBookApi()
 *   const books = await api.listBooks()
 *   await api.generateChapters(17, { start: 3, count: 5 })
 */
import { useRuntimeConfig, navigateTo } from '#imports'

// ===== 内部 HTTP 层 =====
async function _fetch(path: string, opts: RequestInit = {}): Promise<any> {
  const config = useRuntimeConfig()
  const base = import.meta.client ? config.public.apiBase : 'http://localhost:8000'
  const url = `${base}/api${path}`

  let token = ''
  if (import.meta.client) token = localStorage.getItem('moyu_token') || ''

  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(url, { ...opts, headers })
  if (res.status === 401) {
    if (import.meta.client) {
      localStorage.removeItem('moyu_token')
      await navigateTo('/login')
    }
    throw new Error('认证已过期')
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail.detail || detail.message || `HTTP ${res.status}`)
  }
  return res.headers.get('content-type')?.includes('application/json') ? res.json() : res.text()
}

function _pid(): number {
  if (import.meta.client) {
    const m = window.location.pathname.match(/\/projects\/(\d+)/)
    if (m) return Number(m[1])
  }
  return 0
}

function _get(path: string) { return _fetch(path) }
function _post(path: string, body?: any) { return _fetch(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }) }
function _put(path: string, body: any) { return _fetch(path, { method: 'PUT', body: JSON.stringify(body) }) }
function _del(path: string) { return _fetch(path, { method: 'DELETE' }) }

// ===== API 客户端 =====
export function useBookApi() {
  const pid = _pid

  return {
    // ==================== 书 ====================
    listBooks: () => _get('/books'),
    createBook: (title: string, genre = '', synopsis = '', outlineMode = 'one_to_one') =>
      _post('/books', { title, genre, synopsis, outline_mode: outlineMode }),
    getProject: (id?: number) => _get(`/projects/${id || pid()}`),
    updateProject: (body: any, id?: number) => _put(`/projects/${id || pid()}`, body),
    deleteProject: (id: number) => _del(`/projects/${id}`),
    importProject: (data: any) => _post('/projects/import', data),
    exportProject: (id?: number) => _get(`/projects/${id || pid()}/export?format=json`),

    // ==================== 章节 ====================
    /** 章节列表（不含正文 content，有 content_preview） */
    listChapters: (id?: number) => _get(`/projects/${id || pid()}/chapters`),
    /** 单章完整内容 */
    getChapter: (chapterId: number, id?: number) => _get(`/projects/${id || pid()}/chapters/${chapterId}`),
    createChapter: (body: { chapter_number: number; title: string; outline_id?: number }, id?: number) =>
      _post(`/projects/${id || pid()}/chapters`, body),
    updateChapter: (chapterId: number, body: any, id?: number) =>
      _put(`/projects/${id || pid()}/chapters/${chapterId}`, body),
    deleteChapter: (chapterId: number, id?: number) =>
      _del(`/projects/${id || pid()}/chapters/${chapterId}`),
    /** 立即生成章节（同步，阻塞等待） */
    generateChapter: (chapterId: number, id?: number) =>
      _post(`/projects/${id || pid()}/chapters/${chapterId}/generate`),
    /** 异步生成章节（返回 task_id） */
    generateChapterAsync: (
      chapterId: number,
      skillName?: string,
      style?: any,
      opts?: { narrativePov?: string; targetWords?: number; model?: string; thinkingMode?: string },
      id?: number,
    ) => {
      const body: Record<string, any> = {}
      if (skillName) body.skill_name = skillName
      if (style) {
        if (style.config) body.style_config = style.config
        if (style.name) body.style_name = style.name
        if (style.custom_prompt) body.style_custom_prompt = style.custom_prompt
        if (style.style_traits) body.style_traits = style.style_traits
        if (style.reference_text) body.style_reference_text = style.reference_text
      }
      if (opts) {
        if (opts.narrativePov) body.narrative_pov = opts.narrativePov
        if (opts.targetWords) body.target_word_count = opts.targetWords
        if (opts.model) body.model = opts.model
        if (opts.thinkingMode) body.thinking_mode = opts.thinkingMode
      }
      return _post(`/projects/${id || pid()}/chapters/${chapterId}/generate-async`, body)
    },
    /** 批量生成（异步） */
    generateChapters: (
      id: number,
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
    ) => {
      const body: Record<string, any> = {
        target_word_count: opts.targetWords || 2500,
        enable_analysis: opts.enableAnalysis ?? true,
        max_retries: 2,
      }
      if (opts.chapterIds) body.chapter_ids = opts.chapterIds
      else if (opts.start && opts.count) {
        body.start_chapter_number = opts.start
        body.count = opts.count
      }
      if (opts.modelOverride) body.model_override = opts.modelOverride
      if (opts.styleId) body.style_id = opts.styleId
      if (opts.narrativePerspective) body.narrative_perspective = opts.narrativePerspective
      return _post(`/projects/${id}/chapters/batch-generate`, body)
    },
    /** 清空章节 */
    clearChapter: (chapterId: number, cascade = false, id?: number) =>
      _post(`/projects/${id || pid()}/chapters/${chapterId}/clear`, { cascade }),
    /** 重写/润色章节 */
    regenerateChapter: (chapterId: number, instructions = '', id?: number, targetWords?: number) =>
      _post(`/projects/${id || pid()}/chapters/${chapterId}/regenerate`, { instructions, target_word_count: targetWords }),
    /** 获取章节导航（上/下章） */
    getNavigation: (chapterId: number, id?: number) =>
      _get(`/projects/${id || pid()}/chapters/${chapterId}/navigation`),

    // ==================== 大纲 ====================
    listOutlines: (id?: number) => _get(`/projects/${id || pid()}/outlines`),
    createOutline: (body: any, id?: number) => _post(`/projects/${id || pid()}/outlines`, body),
    updateOutline: (outlineId: number, body: any, id?: number) =>
      _put(`/projects/${id || pid()}/outlines/${outlineId}`, body),
    deleteOutline: (outlineId: number, id?: number) =>
      _del(`/projects/${id || pid()}/outlines/${outlineId}`),
    /** 生成大纲（异步） */
    generateOutline: (id: number, chapterCount = 10, narrativePov?: string) =>
      _post(`/projects/${id}/outlines/generate-async`, {
        chapter_count: chapterCount,
        narrative_pov: narrativePov || '',
      }),
    /** 续写大纲 */
    continueOutline: (id: number, body: any = {}) =>
      _post(`/projects/${id}/outlines/continue-async`, body),
    /** 展开大纲（1-N） */
    expandOutline: (outlineId: number, targetCount: number, mode?: string, id?: number) =>
      _post(`/projects/${id || pid()}/outlines/${outlineId}/expand-async`, {
        target_chapter_count: targetCount,
        mode: mode || 'new',
      }),
    /** 批量展开 */
    batchExpandOutlines: (targetCount: number, id?: number) =>
      _post(`/projects/${id || pid()}/outlines/batch-expand-async`, { target_chapter_count: targetCount }),
    /** 大纲下的子章节 */
    getOutlineChapters: (outlineId: number, id?: number) =>
      _get(`/projects/${id || pid()}/outlines/${outlineId}/chapters`),
    deleteOutlineChapters: (outlineId: number, id?: number) =>
      _del(`/projects/${id || pid()}/outlines/${outlineId}/chapters`),
    /** 待补充实体 */
    getPendingEntities: (id?: number) => _get(`/projects/${id || pid()}/outlines/pending-entities`),
    generatePendingEntities: (id?: number) =>
      _post(`/projects/${id || pid()}/outlines/generate-pending-entities`),

    // ==================== 角色 ====================
    listCharacters: (id?: number) => _get(`/projects/${id || pid()}/characters`),
    createCharacter: (body: any, id?: number) => _post(`/projects/${id || pid()}/characters`, body),
    updateCharacter: (characterId: number, body: any, id?: number) =>
      _put(`/projects/${id || pid()}/characters/${characterId}`, body),
    deleteCharacter: (characterId: number, id?: number) =>
      _del(`/projects/${id || pid()}/characters/${characterId}`),

    // ==================== 组织 ====================
    listOrganizations: (id?: number) => _get(`/projects/${id || pid()}/organizations`),
    createOrganization: (body: any, id?: number) =>
      _post(`/projects/${id || pid()}/organizations`, body),
    updateOrganization: (orgId: number, body: any, id?: number) =>
      _put(`/projects/${id || pid()}/organizations/${orgId}`, body),
    deleteOrganization: (orgId: number, id?: number) =>
      _del(`/projects/${id || pid()}/organizations/${orgId}`),

    // ==================== 物品 / 地点 ====================
    listItems: (id?: number) => _get(`/projects/${id || pid()}/items`),
    listLocations: (id?: number) => _get(`/projects/${id || pid()}/locations`),

    // ==================== 世界观 ====================
    listWorlds: (id?: number) => _get(`/projects/${id || pid()}/worldview`),
    createWorld: (body: any, id?: number) => _post(`/projects/${id || pid()}/worldview`, body),
    updateWorld: (worldId: number, body: any, id?: number) =>
      _put(`/projects/${id || pid()}/worldview/${worldId}`, body),
    deleteWorld: (worldId: number, id?: number) =>
      _del(`/projects/${id || pid()}/worldview/${worldId}`),

    // ==================== 伏笔 ====================
    listForeshadows: (status?: string, id?: number) =>
      _get(`/projects/${id || pid()}/foreshadows${status ? `?status=${status}` : ''}`),
    createForeshadow: (body: any, id?: number) =>
      _post(`/projects/${id || pid()}/foreshadows`, body),
    updateForeshadow: (fid: number, body: any, id?: number) =>
      _put(`/projects/${id || pid()}/foreshadows/${fid}`, body),
    deleteForeshadow: (fid: number, id?: number) =>
      _del(`/projects/${id || pid()}/foreshadows/${fid}`),

    // ==================== 剧情分析 ====================
    getAnalysis: (chapterNumber: number, id?: number) =>
      _get(`/projects/${id || pid()}/analyses/${chapterNumber}`),
    triggerAnalysis: (chapterId: number, id?: number) =>
      _post(`/projects/${id || pid()}/chapters/${chapterId}/analyze`),
    analyzeAllUnanalyzed: (id?: number) =>
      _post(`/projects/${id || pid()}/chapters/analyze-all`),

    // ==================== 写作风格 ====================
    listWritingStyles: () => _get('/writing-styles'),

    // ==================== 任务管理 ====================
    getBatchStatus: (taskId: number, id?: number) =>
      _get(`/projects/${id || pid()}/batch-generate/${taskId}/status`),
    getActiveBatchTask: (id?: number) =>
      _get(`/projects/${id || pid()}/batch-generate/active`),
    cancelBatchTask: (taskId: number, id?: number) =>
      _post(`/projects/${id || pid()}/batch-generate/${taskId}/cancel`),
    retryBatchTask: (taskId: number, id?: number) =>
      _post(`/projects/${id || pid()}/batch-generate/${taskId}/retry`),
    getActiveTasks: () => _get('/tasks/active'),
    getTaskStatus: (taskId: number) => _get(`/tasks/${taskId}`),

    // ==================== AI 模型 ====================
    listAiModels: () => _get('/ai-models'),
    createAiModel: (body: any) => _post('/ai-models', body),
    updateAiModel: (modelId: number, body: any) => _put(`/ai-models/${modelId}`, body),
    deleteAiModel: (modelId: number) => _del(`/ai-models/${modelId}`),
    testAiModel: (modelId: number) => _post(`/ai-models/${modelId}/test`),
    fetchDefaultRemoteModels: () => _get('/ai-models/default/remote-models'),

    // ==================== 封面 ====================
    generateCoverPrompt: (id?: number) =>
      _post(`/projects/${id || pid()}/cover/generate-prompt`),
    generateCoverImage: (prompt: string, id?: number) =>
      _post(`/projects/${id || pid()}/cover/generate-image`, { prompt }),

    // ==================== 思考模式 ====================
    getThinkingModes: (id?: number) => _get(`/projects/${id || pid()}/thinking-modes`),
    saveThinkingModes: (modes: Record<string, any>, id?: number) =>
      _put(`/projects/${id || pid()}/thinking-modes`, { modes }),

    // ==================== 灵感模式 ====================
    inspirationStep: (step: string, body: any, id?: number) =>
      _post(`/projects/${id || pid()}/inspiration/step/${step}`, body),
    inspirationQuickComplete: (body: any, id?: number) =>
      _post(`/projects/${id || pid()}/inspiration/quick-complete`, body),

    // ==================== 其他 ====================
    /** 全局统计 */
    getStats: () => _get('/stats'),
    /** 最近编辑 */
    getRecentEdits: () => _get('/recent-edits'),
    /** 注释 */
    getAnnotations: (chapterId: number, id?: number) =>
      _get(`/projects/${id || pid()}/chapters/${chapterId}/annotations`),
    /** 去 AI 味 */
    aiDenoising: (body: { text: string }) =>
      _post(`/projects/${pid()}/ai-denoising`, body),
    /** 清理重复分析 */
    cleanupDuplicateAnalyses: (id?: number) =>
      _post(`/projects/${id || pid()}/chapters/cleanup-duplicate-analyses`),
    /** 异步触发分析 */
    triggerAnalysisAsync: (chapterId: number, id?: number) =>
      _post(`/projects/${id || pid()}/chapters/${chapterId}/analyze`),
    getAnalysisTaskStatus: (chapterId: number, id?: number) =>
      _get(`/projects/${id || pid()}/chapters/${chapterId}/analyze/status`),
    getAnalyses: (id?: number) => _get(`/projects/${id || pid()}/analyses`),
    /** 剧情分析 */
    syncForeshadowsFromAnalysis: (chapterIds?: number[], id?: number) =>
      _post(`/projects/${id || pid()}/chapters/sync-foreshadows`, { chapter_ids: chapterIds }),

    // ==================== 角色扩展 ====================
    getCharacters: (id?: number) => _get(`/projects/${id || pid()}/characters`),
    autoGenerateCharacter: (id?: number) =>
      _post(`/projects/${id || pid()}/characters/generate`),
    autoGenerateCharacterAsync: (body: { count: number; requirements?: string }, id?: number) =>
      _post(`/projects/${id || pid()}/characters/generate-async`, body),
    batchGenerateCharacters: (body: any, id?: number) =>
      _post(`/projects/${id || pid()}/characters/batch-generate`, body),
    batchGenerateCharactersAsync: (body: any, id?: number) =>
      _post(`/projects/${id || pid()}/characters/batch-generate-async`, body),
    getCharacterOrganizations: (characterId: number, id?: number) =>
      _get(`/projects/${id || pid()}/characters/${characterId}/organizations`),
    // 职业
    getCareers: (id?: number) => _get(`/projects/${id || pid()}/careers`),
    createCareer: (body: any, id?: number) => _post(`/projects/${id || pid()}/careers`, body),
    deleteCareer: (careerId: number, id?: number) =>
      _del(`/projects/${id || pid()}/careers/${careerId}`),
    autoAssignCareers: (id?: number) => _post(`/projects/${id || pid()}/careers/auto-assign`),
    getCharCareers: (characterId: number, id?: number) =>
      _get(`/projects/${id || pid()}/characters/${characterId}/careers`),
    createCharCareer: (characterId: number, body: any, id?: number) =>
      _post(`/projects/${id || pid()}/characters/${characterId}/careers`, body),
    updateCharCareer: (ccId: number, body: any, id?: number) =>
      _put(`/projects/${id || pid()}/character-careers/${ccId}`, body),
    deleteCharCareer: (ccId: number, id?: number) =>
      _del(`/projects/${id || pid()}/character-careers/${ccId}`),

    // ==================== 物品/地点 CRUD ====================
    getItems: (id?: number) => _get(`/projects/${id || pid()}/items`),
    createItem: (body: any, id?: number) => _post(`/projects/${id || pid()}/items`, body),
    updateItem: (itemId: number, body: any, id?: number) =>
      _put(`/projects/${id || pid()}/items/${itemId}`, body),
    deleteItem: (itemId: number, id?: number) =>
      _del(`/projects/${id || pid()}/items/${itemId}`),
    generateItems: (id?: number) => _post(`/projects/${id || pid()}/items/generate`),
    getLocations: (id?: number) => _get(`/projects/${id || pid()}/locations`),
    createLocation: (body: any, id?: number) =>
      _post(`/projects/${id || pid()}/locations`, body),
    updateLocation: (locId: number, body: any, id?: number) =>
      _put(`/projects/${id || pid()}/locations/${locId}`, body),
    deleteLocation: (locId: number, id?: number) =>
      _del(`/projects/${id || pid()}/locations/${locId}`),
    generateLocations: (id?: number) => _post(`/projects/${id || pid()}/locations/generate`),
    getLocationTree: (id?: number) => _get(`/projects/${id || pid()}/locations/tree`),

    // ==================== 组织扩展 ====================
    getOrganizations: (id?: number) => _get(`/projects/${id || pid()}/organizations`),
    autoGenerateOrganization: (id?: number) =>
      _post(`/projects/${id || pid()}/organizations/generate`),
    generateOrganizationAsync: (body: any, id?: number) =>
      _post(`/projects/${id || pid()}/organizations/generate-async`, body),
    getOrgMembers: (orgId: number, id?: number) =>
      _get(`/projects/${id || pid()}/organizations/${orgId}/members`),
    addOrgMember: (orgId: number, body: any, id?: number) =>
      _post(`/projects/${id || pid()}/organizations/${orgId}/members`, body),
    updateOrgMember: (memberId: number, body: any, id?: number) =>
      _put(`/projects/${id || pid()}/organization-members/${memberId}`, body),
    removeOrgMember: (memberId: number, id?: number) =>
      _del(`/projects/${id || pid()}/organization-members/${memberId}`),
    generateOrgMembers: (orgId: number, id?: number) =>
      _post(`/projects/${id || pid()}/organizations/${orgId}/members/generate`),
    generateAllOrgMembers: (id?: number) =>
      _post(`/projects/${id || pid()}/organizations/members/generate-all`),
    getOrgTree: (id?: number) => _get(`/projects/${id || pid()}/organizations/tree`),
    updateOrgTree: (body: any, id?: number) =>
      _put(`/projects/${id || pid()}/organizations/tree`, body),
    autoAnalyzeOrganizations: (id?: number) =>
      _post(`/projects/${id || pid()}/organizations/auto-analyze`),

    // ==================== 世界观扩展 ====================
    getWorlds: (id?: number) => _get(`/projects/${id || pid()}/worldview`),
    getWorldCore: (id?: number) => _get(`/projects/${id || pid()}/worldview/core`),
    generateWorld: (body: any, id?: number) =>
      _post(`/projects/${id || pid()}/worldview/generate`, body),
    generateWorldCore: (body: any, id?: number) =>
      _post(`/projects/${id || pid()}/worldview/generate-core`, body),
    updateWorldCore: (body: any, id?: number) =>
      _put(`/projects/${id || pid()}/worldview/core`, body),
    reindexWorldVectors: (id?: number) =>
      _post(`/projects/${id || pid()}/worldview/reindex`),

    // ==================== 关系 ====================
    getRelations: (id?: number) => _get(`/projects/${id || pid()}/relations`),
    createRelation: (body: any, id?: number) =>
      _post(`/projects/${id || pid()}/relations`, body),
    updateRelation: (relId: number, body: any, id?: number) =>
      _put(`/projects/${id || pid()}/relations/${relId}`, body),
    deleteRelation: (relId: number, id?: number) =>
      _del(`/projects/${id || pid()}/relations/${relId}`),
    getRelationGraph: (id?: number) => _get(`/projects/${id || pid()}/relations/graph`),
    autoRebuildRelations: (id?: number) =>
      _post(`/projects/${id || pid()}/relations/auto-rebuild`),
    getRelationTypes: (id?: number) => _get(`/projects/${id || pid()}/relations/types`),
    renameRelationType: (body: any, id?: number) =>
      _put(`/projects/${id || pid()}/relations/types/rename`, body),
    deleteRelationType: (typeId: number, id?: number) =>
      _del(`/projects/${id || pid()}/relations/types/${typeId}`),
    getRelationChangeLogs: (relId: number, id?: number) =>
      _get(`/projects/${id || pid()}/relations/${relId}/change-logs`),
    createRelationChangeLog: (relId: number, body: any, id?: number) =>
      _post(`/projects/${id || pid()}/relations/${relId}/change-logs`, body),
    deleteRelationChangeLog: (relId: number, logId: number, id?: number) =>
      _del(`/projects/${id || pid()}/relations/${relId}/change-logs/${logId}`),
    getCharacterChangeLogs: (characterId: number, id?: number) =>
      _get(`/projects/${id || pid()}/characters/${characterId}/change-logs`),
    createCharacterChangeLog: (characterId: number, body: any, id?: number) =>
      _post(`/projects/${id || pid()}/characters/${characterId}/change-logs`, body),
    deleteCharacterChangeLog: (characterId: number, logId: number, id?: number) =>
      _del(`/projects/${id || pid()}/characters/${characterId}/change-logs/${logId}`),

    // ==================== 伏笔扩展 ====================
    getForeshadows: (status?: string, id?: number) =>
      _get(`/projects/${id || pid()}/foreshadows${status ? `?status=${status}` : ''}`),
    batchDeleteForeshadows: (ids: number[], id?: number) =>
      _post(`/projects/${id || pid()}/foreshadows/batch-delete`, { ids }),
    planForeshadows: (id?: number) => _post(`/projects/${id || pid()}/foreshadows/plan`),
    plantForeshadow: (fid: number, chapterNumber: number, hintText = '', id?: number) =>
      _post(`/projects/${id || pid()}/foreshadows/${fid}/plant`, { chapter_number: chapterNumber, hint_text: hintText }),
    resolveForeshadow: (fid: number, chapterNumber: number, resolutionText = '', isPartial = false, id?: number) =>
      _post(`/projects/${id || pid()}/foreshadows/${fid}/resolve`, { chapter_number: chapterNumber, resolution_text: resolutionText, is_partial: isPartial }),
    abandonForeshadow: (fid: number, reason = '', id?: number) =>
      _post(`/projects/${id || pid()}/foreshadows/${fid}/abandon`, { reason }),
    getPendingResolve: (currentChapter: number, id?: number) =>
      _get(`/projects/${id || pid()}/foreshadows/pending-resolve?chapter=${currentChapter}`),
    getOverdueForeshadows: (currentChapter: number, id?: number) =>
      _get(`/projects/${id || pid()}/foreshadows/overdue?chapter=${currentChapter}`),

    // ==================== 记忆 ====================
    getMemories: (id?: number) => _get(`/projects/${id || pid()}/memories`),
    createMemory: (body: any, id?: number) => _post(`/projects/${id || pid()}/memories`, body),
    updateMemory: (memId: number, body: any, id?: number) =>
      _put(`/projects/${id || pid()}/memories/${memId}`, body),
    deleteMemory: (memId: number, id?: number) =>
      _del(`/projects/${id || pid()}/memories/${memId}`),
    clearMemories: (id?: number) => _post(`/projects/${id || pid()}/memories/clear`),
    searchMemories: (query: string, id?: number) =>
      _get(`/projects/${id || pid()}/memories/search?q=${encodeURIComponent(query)}`),
    getMemoryStats: (id?: number) => _get(`/projects/${id || pid()}/memories/stats`),
    reindexMemories: (id?: number) => _post(`/projects/${id || pid()}/memories/reindex`),

    // ==================== 重写/润色 ====================
    getRegenTasks: (chapterId: number, id?: number) =>
      _get(`/projects/${id || pid()}/chapters/${chapterId}/regeneration/tasks`),
    getRegenTaskDetail: (chapterId: number, taskId: number, id?: number) =>
      _get(`/projects/${id || pid()}/chapters/${chapterId}/regeneration/${taskId}`),
    applyRegenTask: (chapterId: number, taskId: number, id?: number) =>
      _post(`/projects/${id || pid()}/chapters/${chapterId}/regeneration/${taskId}/apply`),
    partialRegenerate: (chapterId: number, body: any, id?: number) =>
      _post(`/projects/${id || pid()}/chapters/${chapterId}/partial-regenerate`, body),
    applyPartialRegen: (chapterId: number, body: any, id?: number) =>
      _post(`/projects/${id || pid()}/chapters/${chapterId}/apply-partial-regenerate`, body),

    // ==================== 大纲扩展 ====================
    generateOutlines: (chapterCount = 10, id?: number) =>
      _post(`/projects/${id || pid()}/outlines/generate-async`, { chapter_count: chapterCount }),
    generateOutlinesAsync: (chapterCount = 3, id?: number) =>
      _post(`/projects/${id || pid()}/outlines/generate-async`, { chapter_count: chapterCount }),
    continueOutlinesAsync: (body: any, id?: number) =>
      _post(`/projects/${id || pid()}/outlines/continue-async`, body),
    expandOutlineAsync: (outlineId: number, body: any, id?: number) =>
      _post(`/projects/${id || pid()}/outlines/${outlineId}/expand-async`, body),
    batchExpandOutlinesAsync: (body: any, id?: number) =>
      _post(`/projects/${id || pid()}/outlines/batch-expand-async`, body),

    // ==================== 提示词模板 ====================
    listPromptTemplates: () => _get('/prompt-templates'),
    getPromptTemplate: (id: number) => _get(`/prompt-templates/${id}`),
    createPromptTemplate: (body: any) => _post('/prompt-templates', body),
    deletePromptTemplate: (id: number) => _del(`/prompt-templates/${id}`),
    listPromptVersions: (templateId: number) => _get(`/prompt-templates/${templateId}/versions`),
    createPromptVersion: (templateId: number, body: any) =>
      _post(`/prompt-templates/${templateId}/versions`, body),
    activatePromptVersion: (templateId: number, versionId: number) =>
      _post(`/prompt-templates/${templateId}/versions/${versionId}/activate`),

    // ==================== Skill ====================
    createSkill: (body: any) => _post('/skills', body),
    updateSkill: (skillId: number, body: any) => _put(`/skills/${skillId}`, body),
    deleteCustomSkill: (skillId: number) => _del(`/skills/${skillId}`),
    resetSkill: (skillId: number) => _post(`/skills/${skillId}/reset`),
    resetAllSkills: () => _post('/skills/reset-all'),
    reloadSkills: () => _post('/skills/reload'),

    // ==================== 书导入 ====================
    parseTxt: (body: any) => _post('/projects/book-import/parse-txt', body),
    fullImport: (body: any) => _post('/projects/book-import/full-import', body),
    bookImportSuggest: (body: any) => _post('/book-import/reverse-suggest', body),
    bookImportReverseOutlines: (body: any) => _post('/book-import/reverse-outlines', body),
    bookImportDeconstruct: (bookId: number) => _post(`/book-import/${bookId}/deconstruct`),
    uploadBookImport: (body: any) => _post('/book-import/upload', body),
    getImportedBook: (bookId: number) => _get(`/book-import/${bookId}`),
    deleteImportedBook: (bookId: number) => _del(`/book-import/${bookId}`),

    // ==================== MCP ====================
    mcpWorldPlanning: (body: any, id?: number) =>
      _post(`/projects/${id || pid()}/mcp/world-planning`, body),
    mcpCharacterPlanning: (body: any, id?: number) =>
      _post(`/projects/${id || pid()}/mcp/character-planning`, body),

    // ==================== AI 扩展 ====================
    testRewrite: (baseUrl: string, apiKey: string, model: string) =>
      _post('/ai-models/test-rewrite', { base_url: baseUrl, api_key: apiKey, model }),
    testEmbedding: (baseUrl: string, apiKey: string, embeddingModel: string) =>
      _post('/ai-models/test-embedding', { base_url: baseUrl, api_key: apiKey, embedding_model: embeddingModel }),
    fetchRemoteModels: (baseUrl: string, apiKey: string, provider = 'openai') =>
      _post('/ai-models/fetch-remote', { base_url: baseUrl, api_key: apiKey, provider }),
    fetchModelRemoteModels: (modelId: number) =>
      _get(`/ai-models/${modelId}/remote-models`),
    fetchRewriteRemoteModels: (baseUrl: string, apiKey: string) =>
      _post('/ai-models/fetch-rewrite-models', { base_url: baseUrl, api_key: apiKey }),

    // ==================== 全局灵感 ====================
    globalInspirationStep: (step: string, body: any) =>
      _post(`/global-inspiration/step/${step}`, body),
    globalInspirationQuickComplete: (body: any) =>
      _post('/global-inspiration/quick-complete', body),

    // ==================== 别名（兼容旧命名） ====================
    getChapters: function (id?: number) { return this.listChapters(id) },
    getOutlines: function (id?: number) { return this.listOutlines(id) },
    batchGenerate: function (body: any, id?: number) {
      return this.generateChapters(id || _pid(), {
        start: body.start_chapter_number,
        count: body.count,
        chapterIds: body.chapter_ids,
        targetWords: body.target_word_count,
        modelOverride: body.model_override,
        styleId: body.style_id,
        narrativePerspective: body.narrative_perspective,
        enableAnalysis: body.enable_analysis,
      })
    },
    deleteProjectById: function (id: number) { return this.deleteProject(id) },
    generateChapterAsyncCompat: function (chapterId: number, skillName?: string, style?: any, opts?: any, id?: number) {
      return this.generateChapterAsync(chapterId, skillName, style, opts, id)
    },
    pid: () => _pid(),
  }
}
