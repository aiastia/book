// 项目级 API 封装：对接后端 /api/projects/{id}/... 全套接口
// 所有方法基于当前选中的项目（useProject.currentProjectId）
// 用法：
//   const api = useProjectApi()
//   const { data: chapters } = await api.getChapters()
//   await api.generateChapter(chapterId)
import { useApi, apiGet, apiPost, apiPut, apiDelete } from './useApi'
import { useProject } from './useProject'

export function useProjectApi() {
  const { currentProjectId } = useProject()

  /** 获取当前项目 ID（可能为 null，调用方需判断）。
   *  不抛错 —— SSR 阶段读不到项目 ID 时返回 null，让请求被跳过，避免页面 500。
   */
  function pid(): number | null {
    return currentProjectId.value ?? null
  }

  /** 项目级 GET（SSR 友好）。无项目 ID 时跳过请求，返回空数据。 */
  function get<T>(path: string, key: string) {
    const id = pid()
    // 无项目 ID（SSR 阶段或未选项目）：用空 key，避免发请求
    const url = id ? `/api/projects/${id}${path}` : null
    return useApi<T>(url || '/api/_skip', { key: id ? `${key}-${id}` : `${key}-skip`, server: !!id })
  }

  // ---- 项目 CRUD ----
  const listProjects = () => useApi<any[]>('/api/projects', { key: 'projects' })

  function getProject() {
    return useApi<any>(pid() ? `/api/projects/${pid()}` : '/api/_skip', { key: `project-${pid() || 'skip'}` })
  }

  function createProject(body: { title: string; genre?: string; synopsis?: string; target_word_count?: number }) {
    return apiPost<{ id: number; title: string }>('/api/projects', body)
  }

  function updateProject(body: any) {
    return apiPut(`/api/projects/${pid()}`, body)
  }

  function deleteProjectById(id: number) {
    return apiDelete(`/api/projects/${id}`)
  }

  // ---- 项目导入导出 ----
  function importProject(data: any) {
    return apiPost<any>(`/api/projects/import`, data)
  }

  // ---- 大纲 ----
  function getOutlines() {
    return get<any[]>('/outlines', 'outlines')
  }

  function generateOutlines(chapterCount: number = 10) {
    return apiPost<{ outlines: any[]; count: number }>(`/api/projects/${pid()}/outlines/generate`, { chapter_count: chapterCount }, { timeout: 60000 })
  }
  function generateOutlinesAsync(chapterCount: number = 3) {
    return apiPost<{ task_id: number }>(`/api/projects/${pid()}/outlines/generate-async`, { chapter_count: chapterCount }, { timeout: 10000 })
  }

  function createOutline(body: any) {
    return apiPost(`/api/projects/${pid()}/outlines`, body)
  }

  function updateOutline(outlineId: number, body: any) {
    return apiPut(`/api/projects/${pid()}/outlines/${outlineId}`, body)
  }

  function deleteOutline(outlineId: number) {
    return apiDelete(`/api/projects/${pid()}/outlines/${outlineId}`)
  }

  // ---- 章节 ----
  function getChapters() {
    return get<any[]>('/chapters', 'chapters')
  }

  function getChapter(chapterId: number) {
    return useApi<any>(pid() ? `/api/projects/${pid()}/chapters/${chapterId}` : '/api/_skip', { key: `chapter-${pid() || 'skip'}-${chapterId}` })
  }

  function createChapter(body: {
    chapter_number: number; title?: string; content?: string;
    outline_id?: number | null; sub_index?: number;
    expansion_plan?: Record<string, any> | null; generation_mode?: string;
  }) {
    return apiPost<{ id: number; chapter_number: number }>(`/api/projects/${pid()}/chapters`, body)
  }

  function updateChapter(chapterId: number, body: {
    title?: string; content?: string; status?: string;
    expansion_plan?: Record<string, any> | null;
  }) {
    return apiPut(`/api/projects/${pid()}/chapters/${chapterId}`, body)
  }

  function deleteChapter(chapterId: number) {
    return apiDelete(`/api/projects/${pid()}/chapters/${chapterId}`)
  }

  /** AI 生成章节正文（后台非流式） */
  function generateChapter(chapterId: number) {
    return apiPost<any>(`/api/projects/${pid()}/chapters/${chapterId}/generate`, {}, { timeout: 300000 })
  }
  function generateChapterAsync(chapterId: number, skillName?: string) {
    return apiPost<{ task_id: number }>(`/api/projects/${pid()}/chapters/${chapterId}/generate-async`, skillName ? { skill_name: skillName } : {}, { timeout: 10000 })
  }

  /** 清空章节内容 */
  function clearChapter(chapterId: number) {
    return apiPost<{ ok: boolean; chapter_id: number }>(`/api/projects/${pid()}/chapters/${chapterId}/clear`, {})
  }

  // ---- 角色 ----
  function getCharacters() {
    return get<any[]>('/characters', 'characters')
  }

  function createCharacter(body: any) {
    return apiPost(`/api/projects/${pid()}/characters`, body)
  }

  function updateCharacter(characterId: number, body: any) {
    return apiPut(`/api/projects/${pid()}/characters/${characterId}`, body)
  }

  function deleteCharacter(characterId: number) {
    return apiDelete(`/api/projects/${pid()}/characters/${characterId}`)
  }

  // ---- 世界观 ----
  function getWorlds() {
    return get<any[]>('/worlds', 'worlds')
  }

  function createWorld(body: { name: string; category?: string; content: string }) {
    return apiPost<any>(`/api/projects/${pid()}/worlds`, body)
  }
  function updateWorld(worldId: number, body: any) {
    return apiPut<any>(`/api/projects/${pid()}/worlds/${worldId}`, body)
  }
  function deleteWorld(worldId: number) {
    return apiDelete(`/api/projects/${pid()}/worlds/${worldId}`)
  }

  function generateWorld(body: { genre?: string; idea?: string }) {
    return apiPost<any>(`/api/projects/${pid()}/worlds/generate`, body, { timeout: 120000 })
  }
  function reindexWorldVectors() {
    return apiPost<{ ok: boolean; total: number; message: string }>(`/api/projects/${pid()}/worlds/reindex-vectors`, {}, { timeout: 10000 })
  }

  // ---- 组织 ----
  function getOrganizations() {
    return get<any[]>('/organizations', 'organizations')
  }

  function createOrganization(body: { name: string; org_type?: string; description?: string }) {
    return apiPost(`/api/projects/${pid()}/organizations`, body)
  }

  function deleteOrganization(orgId: number) {
    return apiDelete(`/api/projects/${pid()}/organizations/${orgId}`)
  }
  function updateOrganization(orgId: number, body: any) {
    return apiPut(`/api/projects/${pid()}/organizations/${orgId}`, body)
  }

  // ---- 伏笔 ----
  function getForeshadows(status?: string) {
    const query = status ? `?status=${status}` : ''
    return useApi<any[]>(pid() ? `/api/projects/${pid()}/foreshadows${query}` : '/api/_skip', { key: `foreshadows-${pid() || 'skip'}-${status || 'all'}` })
  }

  function createForeshadow(body: any) {
    return apiPost(`/api/projects/${pid()}/foreshadows`, body)
  }

  function updateForeshadow(foreshadowId: number, body: any) {
    return apiPut(`/api/projects/${pid()}/foreshadows/${foreshadowId}`, body)
  }

  function deleteForeshadow(foreshadowId: number) {
    return apiDelete(`/api/projects/${pid()}/foreshadows/${foreshadowId}`)
  }

  /** AI 自动规划伏笔 */
  function planForeshadows() {
    return apiPost<{ foreshadows: any[]; count: number }>(`/api/projects/${pid()}/foreshadows/plan`, {}, { timeout: 60000 })
  }
  // ===== #15 伏笔闭环 =====
  function plantForeshadow(id: number, chapterNumber: number, hintText: string = '') {
    return apiPost(`/api/projects/${pid()}/foreshadows/${id}/plant`, { chapter_number: chapterNumber, hint_text: hintText })
  }
  function resolveForeshadow(id: number, chapterNumber: number, resolutionText: string = '', isPartial: boolean = false) {
    return apiPost(`/api/projects/${pid()}/foreshadows/${id}/resolve`, { chapter_number: chapterNumber, resolution_text: resolutionText, is_partial: isPartial })
  }
  function abandonForeshadow(id: number, reason: string = '') {
    return apiPost(`/api/projects/${pid()}/foreshadows/${id}/abandon`, { reason })
  }
  function getPendingResolve(currentChapter: number) {
    return apiGet<any>(`/api/projects/${pid()}/foreshadows/pending-resolve?current_chapter=${currentChapter}`)
  }
  function getOverdueForeshadows(currentChapter: number) {
    return apiGet<any[]>(`/api/projects/${pid()}/foreshadows/overdue?current_chapter=${currentChapter}`)
  }
  function syncForeshadowsFromAnalysis(chapterIds?: number[]) {
    return apiPost<{ synced: boolean; planted: number; resolved: number }>(`/api/projects/${pid()}/foreshadows/sync-from-analysis`, { chapter_ids: chapterIds })
  }
  // ===== #8 章节阅读器标注 =====
  function getAnnotations(chapterId: number) {
    return apiGet<{ annotations: any[]; summary: any }>(`/api/projects/${pid()}/chapters/${chapterId}/annotations`)
  }

  // ---- 剧情分析 ----
  function getAnalyses() {
    return get<any[]>('/analyses', 'analyses')
  }

  function getAnalysis(chapterNumber: number) {
    return useApi<any>(pid() ? `/api/projects/${pid()}/analyses/${chapterNumber}` : '/api/_skip', { key: `analysis-${pid() || 'skip'}-${chapterNumber}` })
  }
  function triggerAnalysisAsync(chapterId: number) {
    return apiPost<{ task_id: number; chapter_id: number; status: string }>(`/api/projects/${pid()}/chapters/${chapterId}/analyze`, {}, { timeout: 10000 })
  }
  /** 同步别名：现已改为异步（返回 task_id），保留旧名兼容旧调用方 */
  function triggerAnalysis(chapterId: number) {
    return triggerAnalysisAsync(chapterId)
  }
  function getAnalysisTaskStatus(chapterId: number) {
    return apiGet<any>(`/api/projects/${pid()}/chapters/${chapterId}/analyze/status`)
  }
  function analyzeAllUnanalyzed() {
    return apiPost<{ task_id: number | null; analyzed: number; total: number; total_chapters: number; status: string }>(`/api/projects/${pid()}/chapters/analyze-all`, {}, { timeout: 10000 })
  }
  function getNavigation(chapterId: number) {
    return apiGet<{ current: { id: number; chapter_number: number; title: string }; previous: any | null; next: any | null }>(`/api/projects/${pid()}/chapters/${chapterId}/navigation`)
  }

  // ---- 灵感模式 ----
  function globalInspirationStep(step: string, body: { initial_idea: string; title?: string; description?: string; theme?: string }) {
    return apiPost<{ prompt: string; options: string[] }>(`/api/projects/global-inspiration/step/${step}`, body, { timeout: 60000 })
  }

  function inspirationQuickComplete(body: { initial_idea: string; title?: string; description?: string; theme?: string }) {
    return apiPost<any>(`/api/projects/${pid()}/inspiration/quick-complete`, body, { timeout: 60000 })
  }

  function globalInspirationQuickComplete(body: { initial_idea: string; title?: string; description?: string; theme?: string }) {
    return apiPost<any>('/api/projects/global-inspiration/quick-complete', body, { timeout: 60000 })
  }

  // ---- 大纲续写/展开 ----
  function continueOutlinesAsync(body: { chapter_count: number }) {
    return apiPost<{ task_id: number }>(`/api/projects/${pid()}/outlines/continue-async`, body, { timeout: 10000 })
  }

  function expandOutline(outlineId: number, body: { target_chapter_count: number }) {
    return apiPost<{ expanded: any[]; count: number; start_chapter: number }>(`/api/projects/${pid()}/outlines/${outlineId}/expand`, body, { timeout: 120000 })
  }
  function expandOutlineAsync(outlineId: number, body: { target_chapter_count: number; mode?: 'new' | 'replace' | 'append'; strategy?: string }) {
    return apiPost<{ task_id: number }>(`/api/projects/${pid()}/outlines/${outlineId}/expand-async`, body, { timeout: 10000 })
  }
  function batchExpandOutlinesAsync(body: { target_chapter_count: number }) {
    return apiPost<{ task_id: number; pending_count: number }>(`/api/projects/${pid()}/outlines/batch-expand-async`, body, { timeout: 10000 })
  }
  function getOutlineChapters(outlineId: number) {
    return apiGet<{ has_chapters: boolean; chapter_count: number; chapters: any[] }>(`/api/projects/${pid()}/outlines/${outlineId}/chapters`)
  }
  function deleteOutlineChapters(outlineId: number) {
    return apiDelete<{ ok: boolean; deleted: number }>(`/api/projects/${pid()}/outlines/${outlineId}/chapters`)
  }

  // ---- 角色高级功能 ----
  function batchGenerateCharacters(body: { count: number; requirements?: string }) {
    return apiPost<{ characters: any[]; count: number }>(`/api/projects/${pid()}/characters/batch-generate`, body, { timeout: 60000 })
  }
  function batchGenerateCharactersAsync(body: { count: number; requirements?: string }) {
    return apiPost<{ task_id: number }>(`/api/projects/${pid()}/characters/batch-generate-async`, body, { timeout: 10000 })
  }

  function autoGenerateCharacter(body: { analysis_result?: any; specification?: string }) {
    return apiPost<any>(`/api/projects/${pid()}/characters/auto-generate`, body, { timeout: 60000 })
  }
  function autoGenerateCharacterAsync(body: { analysis_result?: any; specification?: string }) {
    return apiPost<{ task_id: number }>(`/api/projects/${pid()}/characters/auto-generate-async`, body, { timeout: 10000 })
  }

  // ---- 角色变化日志 ----
  function getCharacterChangeLogs(characterId: number) {
    return useApi<any[]>(`/api/projects/${pid()}/characters/${characterId}/change-logs`, { key: `change-logs-${characterId}` })
  }
  function createCharacterChangeLog(characterId: number, body: { chapter_number: number; summary?: string; changed_fields?: Record<string, any> }) {
    return apiPost<any>(`/api/projects/${pid()}/characters/${characterId}/change-logs`, body)
  }
  function deleteCharacterChangeLog(characterId: number, logId: number) {
    return apiDelete(`/api/projects/${pid()}/characters/${characterId}/change-logs/${logId}`)
  }
  function getCharacterOrganizations(characterId: number) {
    return useApi<any[]>(`/api/projects/${pid()}/characters/${characterId}/organizations`, { key: `char-orgs-${characterId}` })
  }

  // ---- 组织 AI 生成 ----
  function generateOrganizationAsync(body: { count?: number; user_input?: string }) {
    return apiPost<{ task_id: number }>(`/api/projects/${pid()}/organizations/generate-async`, body, { timeout: 10000 })
  }

  function autoAnalyzeOrganizations() {
    return apiPost<any>(`/api/projects/${pid()}/organizations/auto-analysis`, {}, { timeout: 60000 })
  }

  function autoGenerateOrganization(body: { analysis_result?: any; specification?: string }) {
    return apiPost<any>(`/api/projects/${pid()}/organizations/auto-generate`, body, { timeout: 60000 })
  }

  function generateCareerSystem(body?: { append?: boolean; count?: number; career_type?: string; user_prompt?: string }) {
    return apiPost<any>(`/api/projects/${pid()}/career-system/generate`, body || {}, { timeout: 120000 })
  }

  // ---- AI 去味 ----
  function aiDenoising(body: { text: string }) {
    return apiPost<{ processed_text: string }>(`/api/projects/${pid()}/ai-denoising`, body, { timeout: 60000 })
  }

  // ---- 封面提示词 ----
  function generateCoverPrompt() {
    return apiPost<{ cover_prompt: string }>(`/api/projects/${pid()}/cover/generate-prompt`, {}, { timeout: 60000 })
  }

  // ---- 拆书导入反向解析 ----
  function bookImportSuggest(body: { title?: string; sampled_text: string }) {
    return apiPost<any>('/api/projects/book-import/reverse-suggest', body, { timeout: 30000 })
  }

  function bookImportReverseOutlines(body: { project_id: number; start_chapter: number; end_chapter: number; chapters_text: string }) {
    return apiPost<{ outlines: any[]; count: number }>('/api/projects/book-import/reverse-outlines', body, { timeout: 60000 })
  }

  // ---- MCP 增强 ----
  function mcpWorldPlanning() {
    return apiPost<any>(`/api/projects/${pid()}/mcp/world-planning`, {}, { timeout: 60000 })
  }

  function mcpCharacterPlanning() {
    return apiPost<any>(`/api/projects/${pid()}/mcp/character-planning`, {}, { timeout: 60000 })
  }

  // ---- AI 模型配置（全局接口，不依赖项目 ID） ----
  const listAiModels = () => useApi<any[]>('/api/ai-models', { key: 'ai-models' })

  function createAiModel(body: any) {
    return apiPost<{ id: number; name: string }>('/api/ai-models', body)
  }

  function updateAiModel(modelId: number, body: any) {
    return apiPut(`/api/ai-models/${modelId}`, body)
  }

  function deleteAiModel(modelId: number) {
    return apiDelete(`/api/ai-models/${modelId}`)
  }

  /** 测试 AI 模型连通性 */
  function testAiModel(modelId: number) {
    return apiPost<{ ok: boolean; reply: string; model: string }>(`/api/ai-models/${modelId}/test`, {}, { timeout: 30000 })
  }

  /** 从远程 API 获取可用模型列表 */
  function fetchRemoteModels(baseUrl: string, apiKey: string, provider: string = 'openai') {
    return apiPost<{ models: Array<{ id: string; owned_by: string }> }>('/api/ai-models/fetch-remote', { base_url: baseUrl, api_key: apiKey, provider }, { timeout: 15000 })
  }

  /** 用默认 AI 模型配置的凭据实时拉取远端模型列表（无需重复填 key） */
  function fetchDefaultRemoteModels() {
    return apiGet<{ models: Array<{ id: string; owned_by: string }>; default_model: string; config_name: string }>('/api/ai-models/default/remote-models', { timeout: 15000 })
  }

  /** 用指定 AI 模型配置的已存凭据拉取远端模型列表（编辑时无需重复填 Key） */
  function fetchModelRemoteModels(modelId: number) {
    return apiGet<{ models: Array<{ id: string; owned_by: string }>; config_name: string }>(`/api/ai-models/${modelId}/remote-models`, { timeout: 15000 })
  }

  /** 测试 embedding 接口连通性（用于记忆向量检索） */
  function testEmbedding(baseUrl: string, apiKey: string, embeddingModel: string) {
    return apiPost<{ ok: boolean; dim: number; model: string }>('/api/ai-models/test-embedding', { base_url: baseUrl, api_key: apiKey, embedding_model: embeddingModel }, { timeout: 30000 })
  }

  // ---- Skill 管理（全局接口，不依赖项目 ID） ----
  const listSkills = () => useApi<any[]>('/api/skills', { key: 'skills' })

  function updateSkill(skillId: number, body: { system_prompt?: string; is_enabled?: boolean; is_customized?: boolean; config?: any }) {
    return apiPut(`/api/skills/${skillId}`, body)
  }

  function resetSkill(skillId: number) {
    return apiPost(`/api/skills/${skillId}/reset`, {})
  }

  /** 一键重置所有 Skill 为系统默认（清除所有用户自定义） */
  function resetAllSkills() {
    return apiPost('/api/skills/reset-all', {})
  }

  /** 用户自定义创建 Skill */
  function createSkill(body: { name: string; display_name?: string; description?: string; category?: string; system_prompt: string }) {
    return apiPost<{ ok: boolean; id: number; name: string }>('/api/skills/create', body)
  }

  /** 删除自定义 Skill */
  function deleteCustomSkill(skillId: number) {
    return apiDelete(`/api/skills/${skillId}/custom`)
  }

  // ---- Prompt Template 版本管理 ----
  function listPromptTemplates(category?: string) {
    const query = category ? `?category=${category}` : ''
    return useApi<any[]>(`/api/prompt-templates${query}`, { key: `prompt-templates-${category || 'all'}` })
  }

  // ============ 核心世界观（时间/地点/氛围/规则） ============
  function getWorldCore() {
    return useApi<any>(pid() ? `/api/projects/${pid()}/world-core` : '/api/_skip', { key: `world-core-${pid() || 'skip'}` })
  }
  function updateWorldCore(body: any) {
    return apiPut(`/api/projects/${pid()}/world-core`, body)
  }
  function generateWorldCore() {
    return apiPost(`/api/projects/${pid()}/world-core/generate`, {}, { timeout: 120000 })
  }

  // ============ 角色关系 ============
  function getRelations() {
    return useApi<any[]>(pid() ? `/api/projects/${pid()}/relations` : '/api/_skip', { key: `relations-${pid() || 'skip'}` })
  }
  function getRelationGraph() {
    return useApi<any>(pid() ? `/api/projects/${pid()}/relations/graph` : '/api/_skip', { key: `relation-graph-${pid() || 'skip'}` })
  }
  function autoRebuildRelations() {
    return apiPost(`/api/projects/${pid()}/relations/auto-rebuild`, {}, { timeout: 180000 })
  }
  function createRelation(body: any) {
    return apiPost(`/api/projects/${pid()}/relations`, body)
  }
  function deleteRelation(id: number) {
    return apiDelete(`/api/projects/${pid()}/relations/${id}`)
  }
  function updateRelation(relationId: number, body: any) {
    return apiPut(`/api/projects/${pid()}/relations/${relationId}`, body)
  }

  // ---- 关系变化日志 ----
  function getRelationChangeLogs(relationId: number) {
    return useApi<any[]>(`/api/projects/${pid()}/relations/${relationId}/change-logs`, { key: `rel-change-logs-${relationId}` })
  }
  function createRelationChangeLog(relationId: number, body: { chapter_number: number; summary?: string; changed_fields?: Record<string, any> }) {
    return apiPost<any>(`/api/projects/${pid()}/relations/${relationId}/change-logs`, body)
  }
  function deleteRelationChangeLog(relationId: number, logId: number) {
    return apiDelete(`/api/projects/${pid()}/relations/${relationId}/change-logs/${logId}`)
  }

  // ---- 关系类型管理 ----
  function getRelationTypes() {
    return useApi<any[]>(pid() ? `/api/projects/${pid()}/relations/types` : '/api/_skip', { key: `relation-types-${pid() || 'skip'}` })
  }
  function renameRelationType(oldName: string, newName: string) {
    return apiPut(`/api/projects/${pid()}/relations/types/rename`, { old_name: oldName, new_name: newName })
  }
  function deleteRelationType(typeName: string) {
    return apiDelete(`/api/projects/${pid()}/relations/types/${encodeURIComponent(typeName)}`)
  }

  // ============ 记忆系统 ============
  function getMemories(params: { memory_type?: string; keyword?: string; limit?: number } = {}) {
    const qs = new URLSearchParams()
    if (params.memory_type) qs.set('memory_type', params.memory_type)
    if (params.keyword) qs.set('keyword', params.keyword)
    if (params.limit) qs.set('limit', String(params.limit))
    const query = qs.toString()
    return useApi<any[]>(pid() ? `/api/projects/${pid()}/memories${query ? '?' + query : ''}` : '/api/_skip', { key: `memories-${pid() || 'skip'}-${query}` })
  }
  function getMemoryStats() {
    return useApi<any>(pid() ? `/api/projects/${pid()}/memories/stats` : '/api/_skip', { key: `memory-stats-${pid() || 'skip'}` })
  }
  function createMemory(body: any) {
    return apiPost(`/api/projects/${pid()}/memories`, body)
  }
  function updateMemory(id: number, body: any) {
    return apiPut(`/api/projects/${pid()}/memories/${id}`, body)
  }
  function deleteMemory(id: number) {
    return apiDelete(`/api/projects/${pid()}/memories/${id}`)
  }
  function clearMemories(memory_type?: string) {
    const q = memory_type ? `?memory_type=${memory_type}` : ''
    return apiDelete(`/api/projects/${pid()}/memories${q}`)
  }
  function searchMemories(body: { query: string; memory_types?: string[]; limit?: number; min_importance?: number }) {
    return apiPost<any[]>(`/api/projects/${pid()}/memories/search`, body, { timeout: 30000 })
  }
  function reindexMemories() {
    return apiPost<{ indexed: number; total: number }>(`/api/projects/${pid()}/memories/reindex`, {}, { timeout: 120000 })
  }

  // ============ 职业体系 ============
  function getCareers() {
    return useApi<any[]>(pid() ? `/api/projects/${pid()}/careers` : '/api/_skip', { key: `careers-${pid() || 'skip'}` })
  }
  function createCareer(body: any) {
    return apiPost(`/api/projects/${pid()}/careers`, body)
  }
  function deleteCareer(id: number) {
    return apiDelete(`/api/projects/${pid()}/careers/${id}`)
  }

  // ============ 物品/道具 ============
  function getItems(params: { category?: string; keyword?: string } = {}) {
    const qs = new URLSearchParams()
    if (params.category) qs.set('category', params.category)
    if (params.keyword) qs.set('keyword', params.keyword)
    const query = qs.toString()
    return useApi<any[]>(pid() ? `/api/projects/${pid()}/items${query ? '?' + query : ''}` : '/api/_skip', { key: `items-${pid() || 'skip'}-${query}` })
  }
  function createItem(body: any) { return apiPost(`/api/projects/${pid()}/items`, body) }
  function updateItem(id: number, body: any) { return apiPut(`/api/projects/${pid()}/items/${id}`, body) }
  function deleteItem(id: number) { return apiDelete(`/api/projects/${pid()}/items/${id}`) }
  function generateItems(body: { count?: number; category?: string; user_prompt?: string }) {
    return apiPost<{ count: number; items: any[] }>(`/api/projects/${pid()}/items/generate`, body, { timeout: 60000 })
  }

  // ============ 地点/地图 ============
  function getLocations(params: { location_type?: string; keyword?: string } = {}) {
    const qs = new URLSearchParams()
    if (params.location_type) qs.set('location_type', params.location_type)
    if (params.keyword) qs.set('keyword', params.keyword)
    const query = qs.toString()
    return useApi<any[]>(pid() ? `/api/projects/${pid()}/locations${query ? '?' + query : ''}` : '/api/_skip', { key: `locations-${pid() || 'skip'}-${query}` })
  }
  function getLocationTree() {
    return useApi<any[]>(pid() ? `/api/projects/${pid()}/locations/tree` : '/api/_skip', { key: `location-tree-${pid() || 'skip'}` })
  }
  function createLocation(body: any) { return apiPost(`/api/projects/${pid()}/locations`, body) }
  function updateLocation(id: number, body: any) { return apiPut(`/api/projects/${pid()}/locations/${id}`, body) }
  function deleteLocation(id: number) { return apiDelete(`/api/projects/${pid()}/locations/${id}`) }
  function generateLocations(body: { count?: number; location_type?: string; parent_location_id?: number; user_prompt?: string }) {
    return apiPost<{ count: number; locations: any[] }>(`/api/projects/${pid()}/locations/generate`, body, { timeout: 60000 })
  }

  // ============ 组织树/成员 ============
  function getOrgTree() {
    return useApi<any[]>(pid() ? `/api/projects/${pid()}/organizations/tree` : '/api/_skip', { key: `org-tree-${pid() || 'skip'}` })
  }
  function updateOrgTree(orgId: number, body: any) { return apiPut(`/api/projects/${pid()}/organizations/${orgId}/tree`, body) }
  function getOrgMembers(orgId: number) {
    return useApi<any[]>(pid() ? `/api/projects/${pid()}/organizations/${orgId}/members` : '/api/_skip', { key: `org-members-${orgId}-${pid() || 'skip'}`, server: false })
  }
  function addOrgMember(orgId: number, body: any) { return apiPost(`/api/projects/${pid()}/organizations/${orgId}/members`, body) }
  function updateOrgMember(orgId: number, memberId: number, body: any) { return apiPut(`/api/projects/${pid()}/organizations/${orgId}/members/${memberId}`, body) }
  function removeOrgMember(orgId: number, memberId: number) { return apiDelete(`/api/projects/${pid()}/organizations/${orgId}/members/${memberId}`) }
  function generateOrgMembers(orgId: number, body: { user_prompt?: string }) {
    return apiPost<{ count: number; members: any[] }>(`/api/projects/${pid()}/organizations/${orgId}/members/generate`, body, { timeout: 60000 })
  }
  function generateAllOrgMembers() {
    return apiPost<{ ok: boolean; total: number; created: number; results: any[] }>(`/api/projects/${pid()}/organizations/members/generate-all`, {}, { timeout: 300000 })
  }

  // ============ 角色职业关联 ============
  function getCharCareers(params: { character_id?: number; career_id?: number } = {}) {
    const qs = new URLSearchParams()
    if (params.character_id) qs.set('character_id', String(params.character_id))
    if (params.career_id) qs.set('career_id', String(params.career_id))
    const query = qs.toString()
    return useApi<any[]>(pid() ? `/api/projects/${pid()}/character-careers${query ? '?' + query : ''}` : '/api/_skip', { key: `char-careers-${pid() || 'skip'}-${query}` })
  }
  function createCharCareer(body: any) { return apiPost(`/api/projects/${pid()}/character-careers`, body) }
  function updateCharCareer(ccId: number, body: any) { return apiPut(`/api/projects/${pid()}/character-careers/${ccId}`, body) }
  function deleteCharCareer(ccId: number) { return apiDelete(`/api/projects/${pid()}/character-careers/${ccId}`) }
  function autoAssignCareers(body: { user_prompt?: string }) {
    return apiPost<{ count: number; assignments: any[] }>(`/api/projects/${pid()}/character-careers/auto-assign`, body, { timeout: 60000 })
  }

  // ============ 批量章节生成（#12）============
  // 连续模式：start_chapter_number + count（推荐）；手动模式：chapter_ids（兼容）
  function batchGenerate(body: {
    start_chapter_number?: number
    count?: number
    chapter_ids?: number[]
    enable_analysis?: boolean
    max_retries?: number
    target_word_count?: number
    model_override?: string
    style_id?: number
    narrative_perspective?: string
  }) {
    return apiPost<{ task_id: number; total: number; status: string }>(`/api/projects/${pid()}/chapters/batch-generate`, body)
  }
  function getActiveBatchTask() {
    return apiGet<any | null>(`/api/projects/${pid()}/batch-generate/active`)
  }
  function getBatchStatus(taskId: number) {
    return apiGet<any>(`/api/projects/${pid()}/batch-generate/${taskId}/status`)
  }
  function cancelBatchTask(taskId: number) {
    return apiPost(`/api/projects/${pid()}/batch-generate/${taskId}/cancel`, {})
  }

  // ============ 章节重写（#11 重写历史 + #13 扩写缩写）============
  function regenerateChapter(chapterId: number, body: {
    modification_instructions?: string
    focus_areas?: string[]
    preserve_elements?: string[]
    length_mode?: string
    target_word_count?: number
    version_note?: string
  }) {
    return apiPost<any>(`/api/projects/${pid()}/chapters/${chapterId}/regenerate`, body, { timeout: 300000 })
  }
  function getRegenTasks(chapterId: number) {
    return apiGet<any[]>(`/api/projects/${pid()}/chapters/${chapterId}/regeneration/tasks`)
  }
  function getRegenTaskDetail(chapterId: number, taskId: number) {
    return apiGet<any>(`/api/projects/${pid()}/chapters/${chapterId}/regeneration/${taskId}`)
  }
  function applyRegenTask(chapterId: number, taskId: number) {
    return apiPost(`/api/projects/${pid()}/chapters/${chapterId}/regeneration/${taskId}/apply`, {})
  }
  function partialRegenerate(chapterId: number, body: {
    selected_text: string
    start_position?: number
    end_position?: number
    instructions?: string
    length_mode?: string
  }) {
    return apiPost<any>(`/api/projects/${pid()}/chapters/${chapterId}/partial-regenerate`, body, { timeout: 120000 })
  }
  function applyPartialRegen(chapterId: number, body: { new_text: string; start_position: number; end_position: number }) {
    return apiPost(`/api/projects/${pid()}/chapters/${chapterId}/apply-partial-regenerate`, body)
  }

  // ============ #22 导出（全量JSON + TXT）============
  /** 导出项目数据。format=txt 返回下载 URL（绝对路径）；format=json 返回数据对象。 */
  function exportProject(id: number, format: string = 'json') {
    const config = useRuntimeConfig()
    const base = import.meta.client ? config.public.apiBase : config.apiBase
    if (format === 'txt') {
      return `${base}/api/projects/${id}/export?format=txt`
    }
    return apiGet(`/api/projects/${id}/export?format=json`, { timeout: 30000 })
  }
  // ============ #23 拆书导入解析 ============
  function parseTxt(body: { text?: string; base64?: string }) {
    return apiPost<{ chapters: any[]; stats: any }>('/api/projects/book-import/parse-txt', body, { timeout: 30000 })
  }
  function fullImport(body: { title: string; genre?: string; synopsis?: string; chapters: any[] }) {
    return apiPost<{ project_id: number; title: string; chapter_count: number; total_words: number }>('/api/projects/book-import/full-import', body, { timeout: 60000 })
  }

  // ============ 拆书导入（持久化 + 一键拆解） ============
  /** 上传 TXT 文本到后端解析入库（text 或 base64 二选一）。 */
  function uploadBookImport(body: { filename?: string; title?: string; text?: string; base64?: string }) {
    return apiPost<any>('/api/projects/book-import/upload', body, { timeout: 60000 })
  }

  /** 书籍详情 + 前 10 章预览。 */
  function getImportedBook(id: number) {
    return apiGet<any>(`/api/projects/book-import/${id}`)
  }

  /** 删除导入书籍。 */
  function deleteImportedBook(id: number) {
    return apiDelete(`/api/projects/book-import/${id}`)
  }

  /** 一键拆解：采样立项 + 建项目 + 拆前 N 章大纲（慢，300s）。 */
  function bookImportDeconstruct(bookId: number, body: { sample_side?: 'head' | 'tail'; sample_count?: number; outline_chapters?: number }) {
    return apiPost<{ project_id: number; project_info: any; outline_count: number; batches_done: number }>(
      `/api/projects/book-import/${bookId}/deconstruct`,
      { sample_side: 'head', sample_count: 5, outline_chapters: 20, ...body },
      { timeout: 300000 },
    )
  }

  function getPromptTemplate(id: number) {
    return useApi<any>(`/api/prompt-templates/${id}`, { key: `prompt-template-${id}` })
  }

  function createPromptTemplate(body: { name: string; category?: string; description?: string; system_prompt: string }) {
    return apiPost<{ id: number }>('/api/prompt-templates', body)
  }

  function deletePromptTemplate(id: number) {
    return apiDelete(`/api/prompt-templates/${id}`)
  }

  function listPromptVersions(templateId: number) {
    return apiGet<any[]>(`/api/prompt-templates/${templateId}/versions`)
  }

  function createPromptVersion(templateId: number, body: { system_prompt: string; user_prompt?: string }) {
    return apiPost<{ id: number; version: number }>(`/api/prompt-templates/${templateId}/versions`, body)
  }

  function activatePromptVersion(templateId: number, versionId: number) {
    return apiPost(`/api/prompt-templates/${templateId}/activate/${versionId}`, {})
  }

  return {
    pid,
    // 项目
    listProjects,
    getProject,
    createProject,
    updateProject,
    deleteProjectById,
    exportProject,
    importProject,
    // 大纲
    getOutlines,
    generateOutlines,
    generateOutlinesAsync,
    createOutline,
    updateOutline,
    deleteOutline,
    continueOutlinesAsync,
    expandOutline,
    expandOutlineAsync,
    batchExpandOutlinesAsync,
    getOutlineChapters,
    deleteOutlineChapters,
    // 章节
    getChapters,
    getChapter,
    createChapter,
    updateChapter,
    deleteChapter,
    generateChapter,
    generateChapterAsync,
    clearChapter,
    aiDenoising,
    // 角色
    getCharacters,
    createCharacter,
    updateCharacter,
    deleteCharacter,
    batchGenerateCharacters,
    batchGenerateCharactersAsync,
    autoGenerateCharacter,
    autoGenerateCharacterAsync,
    getCharacterChangeLogs,
    createCharacterChangeLog,
    deleteCharacterChangeLog,
    getCharacterOrganizations,
    // 世界观
    getWorlds,
    createWorld,
    updateWorld,
    deleteWorld,
    generateWorld,
    // 组织
    getOrganizations,
    createOrganization,
    deleteOrganization,
    updateOrganization,
    generateOrganizationAsync,
    autoAnalyzeOrganizations,
    autoGenerateOrganization,
    generateCareerSystem,
    // 伏笔
    getForeshadows,
    createForeshadow,
    updateForeshadow,
    deleteForeshadow,
    planForeshadows,
    plantForeshadow,
    resolveForeshadow,
    abandonForeshadow,
    getPendingResolve,
    getOverdueForeshadows,
    syncForeshadowsFromAnalysis,
    getAnnotations,
    // 核心世界观
    getWorldCore,
    updateWorldCore,
    generateWorldCore,
    // 角色关系
    getRelations,
    getRelationGraph,
    autoRebuildRelations,
    createRelation,
    deleteRelation,
    updateRelation,
    // 关系变化日志
    getRelationChangeLogs,
    createRelationChangeLog,
    deleteRelationChangeLog,
    getRelationTypes,
    renameRelationType,
    deleteRelationType,
    // 记忆系统
    getMemories,
    getMemoryStats,
    createMemory,
    updateMemory,
    deleteMemory,
    clearMemories,
    searchMemories,
    reindexMemories,
    reindexWorldVectors,
    // 职业体系
    getCareers,
    // 物品
    getItems,
    createItem,
    updateItem,
    deleteItem,
    generateItems,
    // 地点
    getLocations,
    getLocationTree,
    createLocation,
    updateLocation,
    deleteLocation,
    generateLocations,
    // 组织树/成员
    getOrgTree,
    updateOrgTree,
    getOrgMembers,
    addOrgMember,
    updateOrgMember,
    removeOrgMember,
    generateOrgMembers,
    generateAllOrgMembers,
    // 角色职业关联
    getCharCareers,
    createCharCareer,
    updateCharCareer,
    deleteCharCareer,
    autoAssignCareers,
    // 批量生成
    batchGenerate,
    getActiveBatchTask,
    getBatchStatus,
    cancelBatchTask,
    // 章节重写
    regenerateChapter,
    getRegenTasks,
    getRegenTaskDetail,
    applyRegenTask,
    partialRegenerate,
    applyPartialRegen,
    parseTxt,
    fullImport,
    uploadBookImport,
    getImportedBook,
    deleteImportedBook,
    bookImportDeconstruct,
    createCareer,
    deleteCareer,
    // 剧情分析
    getAnalyses,
    getAnalysis,
    triggerAnalysis,
    triggerAnalysisAsync,
    getAnalysisTaskStatus,
    analyzeAllUnanalyzed,
    getNavigation,
    // 灵感
    globalInspirationStep,
    globalInspirationQuickComplete,
    // 封面
    generateCoverPrompt,
    // 拆书导入
    bookImportSuggest,
    bookImportReverseOutlines,
    // MCP
    mcpWorldPlanning,
    mcpCharacterPlanning,
    // AI 模型
    listAiModels,
    createAiModel,
    updateAiModel,
    deleteAiModel,
    testAiModel,
    fetchRemoteModels,
    fetchDefaultRemoteModels,
    fetchModelRemoteModels,
    testEmbedding,
    // Skill
    listSkills,
    updateSkill,
    resetSkill,
    resetAllSkills,
    createSkill,
    deleteCustomSkill,
    // Prompt Template
    listPromptTemplates,
    getPromptTemplate,
    createPromptTemplate,
    deletePromptTemplate,
    listPromptVersions,
    createPromptVersion,
    activatePromptVersion,
  }
}