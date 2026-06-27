<script setup lang="ts">
// 故事章节：对标 MuMuAINovel — 双模式列表 + 生成门槛 + 一键分析
import { useProjectApi } from '~/composables/useProjectApi'
import { useProject } from '~/composables/useProject'
import { apiGet } from '~/composables/useApi'
import { fetchWritingStyles, fetchSkills, fetchRemoteModels } from '~/composables/useChapterStream'
import ChapterReaderModal from '~/components/ChapterReaderModal.vue'

useHead({ title: '故事章节 — 墨语' })
const { currentProjectId } = useProject()
if (!currentProjectId.value) await navigateTo('/books')
const api = useProjectApi()
const msg = useMessage()

// ===== 项目信息（含 outline_mode） =====
const { data: projectData } = await api.getProject()
const outlineMode = computed(() => projectData.value?.outline_mode || 'one_to_one')

// ===== 章节 + 大纲数据 =====
const { data: chapters, refresh: refreshList } = await api.getChapters()
const { data: outlines } = await api.getOutlines()

// ===== 编辑器状态 =====
const editorOpen = ref(false)
const editing = ref<any>(null)
const editingContent = ref('')
const rawOutput = ref('')
const showRaw = ref(false)
const editingTitle = ref('')
const generating = ref(false)
const saving = ref(false)
const targetWords = ref(4000)
const narrativePov = ref('')  // 空 = 按小说设定
const projectDefaultPov = ref('第三人称')  // 项目默认叙事视角（用于 placeholder 显示）
if (import.meta.client) {
  const s = localStorage.getItem('moyu_chapter_words')
  if (s) targetWords.value = Number(s)
}

// ===== 编辑器高级选项 =====
const writingStyles = ref<any[]>([])
const selectedStyleId = ref<number | undefined>()
const projectDefaultStyleId = ref<number | undefined>()  // 项目默认风格 ID（用于选项标记）
const availableSkills = ref<any[]>([])
const selectedSkillKey = ref<string | undefined>()
const availableModels = ref<Array<{ value: string; label: string }>>([])
const selectedModel = ref<string | undefined>()
const defaultModelName = ref('')  // 默认模型名（用于 placeholder 显示）
const skillThinkingMode = ref<string | undefined>()

// ===== 章节分析 =====
const analysisPanelRef = ref<any>(null)
const analysisPanelChapter = ref<any>(null)

function openAnalysis(c: any) {
  analysisPanelChapter.value = c
  nextTick(() => {
    analysisPanelRef.value?.open()
  })
}

// ===== 分析建议 → 重写 → 对比 =====
const rewriteCompareOpen = ref(false)
const rewriteOriginal = ref('')
const rewriteNew = ref('')

async function onRewriteWithSuggestions(suggestions: string[]) {
  if (!analysisPanelChapter.value) return
  const ch = analysisPanelChapter.value
  // 把建议拼成修改指令
  const instructions = suggestions.map((s, i) => `${i + 1}. ${s}`).join('\n')
  // 获取原文内容
  const full = await apiGet<any>(`/api/projects/${currentProjectId.value}/chapters/${ch.id}`).catch(() => null)
  rewriteOriginal.value = full?.content || ''
  rewriteNew.value = ''
  rewriteCompareOpen.value = false

  // 调重写 API
  let hide: any = null
  try {
    hide = msg.loading('正在根据建议重写...')
    const r = await api.regenerateChapter(ch.id, {
      modification_instructions: instructions,
      focus_areas: [],
      preserve_elements: [],
      length_mode: 'similar',
      target_word_count: null,
      version_note: '根据分析建议重写',
    })
    hide()
    rewriteNew.value = r?.regenerated_content || ''
    if (rewriteNew.value) {
      rewriteCompareOpen.value = true
    } else {
      msg.warning('重写未返回内容')
    }
  } catch (e: any) {
    if (hide) hide()
    msg.error('重写失败：' + formatError(e))
  }
}

async function onApplyRewriteCompare() {
  if (!analysisPanelChapter.value) return
  const ch = analysisPanelChapter.value
  try {
    await api.updateChapter(ch.id, { content: rewriteNew.value })
    msg.success('已应用新内容')
    rewriteCompareOpen.value = false
    analysisPanelChapter.value = null
    await refreshList()
  } catch (e: any) {
    msg.error('应用失败：' + formatError(e))
  }
}

// ===== 修改弹窗 =====
const modifyOpen = ref(false)
const modifyChapter = ref<any>(null)
const modifyTitle = ref('')
const modifyStatus = ref('draft')

// ===== 搜索与分页 =====
const searchKeyword = ref('')
const pageSize = ref(20)
const currentPage = ref(1)
const pageSizeOptions = ['20', '50', '100']

// ===== 生成门槛逻辑 =====
// 规则：前一章有内容但未分析时，禁止后续生成
const chapterGenerateGateMap = computed(() => {
  const list = chapters.value || []
  const sorted = [...list].sort((a: any, b: any) => a.chapter_number - b.chapter_number)
  const map: Record<number, { canGenerate: boolean; reason: string }> = {}

  for (let i = 0; i < sorted.length; i++) {
    const ch = sorted[i]
    const missing: number[] = []
    let needAnalyze: number | null = null

    for (let j = 0; j < i; j++) {
      const prev = sorted[j]
      if (!prev.word_count || prev.word_count < 50) {
        missing.push(prev.chapter_number)
      }
    }

    // 检查紧邻的前一章：有内容但未分析 → 阻止
    if (i > 0) {
      const prevCh = sorted[i - 1]
      if (prevCh.word_count >= 50 && !prevCh.analyzed) {
        needAnalyze = prevCh.chapter_number
      }
    }

    if (missing.length > 0) {
      map[ch.id] = { canGenerate: false, reason: `需要先完成前置章节：第 ${missing.join('、')} 章` }
    } else if (needAnalyze !== null) {
      map[ch.id] = { canGenerate: false, reason: `请先分析第 ${needAnalyze} 章，再生成后续章节` }
    } else {
      map[ch.id] = { canGenerate: true, reason: '' }
    }
  }
  return map
})

function canGenerateChapter(ch: any): boolean {
  return chapterGenerateGateMap.value[ch.id]?.canGenerate ?? true
}
function getGenerateDisabledReason(ch: any): string {
  return chapterGenerateGateMap.value[ch.id]?.reason || ''
}

// ===== 搜索过滤 + 排序 =====
const filteredChapters = computed(() => {
  const list = chapters.value || []
  const kw = searchKeyword.value.trim().toLowerCase()
  if (!kw) return list
  return list.filter((c: any) => {
    return (
      String(c.chapter_number).includes(kw) ||
      (c.title || '').toLowerCase().includes(kw) ||
      getOutlineTitle(c.outline_id).toLowerCase().includes(kw)
    )
  })
})

const sortedChapters = computed(() => {
  return [...filteredChapters.value].sort((a: any, b: any) => a.chapter_number - b.chapter_number)
})

// ===== 分页 =====
const pagedChapters = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return sortedChapters.value.slice(start, start + pageSize.value)
})

watch([() => chapters.value?.length, pageSize, searchKeyword], () => {
  const total = sortedChapters.value.length
  const maxPage = Math.max(1, Math.ceil(total / pageSize.value))
  if (currentPage.value > maxPage) currentPage.value = maxPage
})

// ===== one-to-many 模式：按大纲分组 =====
interface OutlineGroup {
  outlineId: number | null
  outlineTitle: string
  outlineOrder: number
  chapters: any[]
}

const groupedChapters = computed<OutlineGroup[]>(() => {
  if (outlineMode.value !== 'one_to_many') return []
  const groups: Record<string, any[]> = {}
  for (const ch of sortedChapters.value) {
    const key = ch.outline_id || 'uncategorized'
    if (!groups[key]) groups[key] = []
    groups[key].push(ch)
  }
  const outlineMap = new Map((outlines.value || []).map((o: any) => [o.id, o]))
  return Object.entries(groups)
    .map(([key, chs]) => {
      const outline = key !== 'uncategorized' ? outlineMap.get(Number(key)) : null
      return {
        outlineId: outline?.id ?? null,
        outlineTitle: outline?.title || '未分类',
        outlineOrder: outline?.chapter_number ?? 999,
        chapters: chs,
      }
    })
    .sort((a, b) => a.outlineOrder - b.outlineOrder)
})

const pagedGroupedChapters = computed(() => {
  const groups = groupedChapters.value
  const flat: Array<{ group: OutlineGroup; chapter: any }> = []
  for (const g of groups) {
    for (const ch of g.chapters) {
      flat.push({ group: g, chapter: ch })
    }
  }
  const start = (currentPage.value - 1) * pageSize.value
  const sliced = flat.slice(start, start + pageSize.value)

  const result: OutlineGroup[] = []
  const groupMap = new Map<string, OutlineGroup>()
  for (const { group, chapter } of sliced) {
    const key = String(group.outlineId ?? 'uncategorized')
    if (!groupMap.has(key)) {
      const g = { ...group, chapters: [] }
      groupMap.set(key, g)
      result.push(g)
    }
    groupMap.get(key)!.chapters.push(chapter)
  }
  return result
})

// ===== 已创建章节的章节号集合 =====
const createdChapterNos = computed(() => new Set((chapters.value || []).map((c: any) => c.chapter_number)))

// ===== 大纲标题映射 =====
function getOutlineTitle(outlineId: number | null): string {
  if (!outlineId) return ''
  const o = (outlines.value || []).find((o: any) => o.id === outlineId)
  return o?.title || ''
}

// ===== 可分析章节数 =====
const batchAnalyzableCount = computed(() => {
  return (chapters.value || []).filter((c: any) => c.word_count >= 50 && (!c.analyzed || !c.summary)).length
})

// ===== 状态文本/颜色 =====
const statusText = (s: string) => ({ draft: '草稿', generating: '创作中', completed: '已完成' }[s] || s)
const statusColor = (s: string) => ({ draft: 'default', generating: 'processing', completed: 'success' }[s] || 'default')

// ===== 一键分析（异步后台任务）=====
const { trackTask: trackBgTask, onTaskCompleted } = useBackgroundTasks()

// 当章节生成/批量生成/分析任务完成时自动刷新列表
onTaskCompleted('chapter', () => {
  refreshList()
})
onTaskCompleted('init', () => {
  // 项目初始化完成后也刷新（大纲/章节可能变化）
  setTimeout(() => refreshList(), 2000)
})
const batchAnalyzing = ref(false)
const cleaningUp = ref(false)
async function onCleanupAnalyses() {
  cleaningUp.value = true
  try {
    const res = await api.cleanupDuplicateAnalyses()
    msg.success(`已清理 ${res?.deleted ?? 0} 条重复分析记录`)
  } catch (e: any) { msg.error('清理失败：' + formatError(e)) }
  finally { cleaningUp.value = false }
}
async function onBatchAnalyze() {
  batchAnalyzing.value = true
  try {
    const res = await api.analyzeAllUnanalyzed()
    if (res?.task_id) {
      trackBgTask({ id: res.task_id, task_type: 'chapter_batch_analyze', title: '批量剧情分析', status: 'pending' })
      msg.success('批量分析任务已提交，可在右下角查看进度')
    } else {
      msg.info('没有需要分析的章节')
    }
  } catch (e: any) {
    msg.error('批量分析失败：' + formatError(e))
  } finally {
    batchAnalyzing.value = false
  }
}

// ===== 导出 TXT =====
async function onExportTxt() {
  if (!chapters.value?.length) { msg.warning('暂无章节，无法导出'); return }
  const title = projectData.value?.title || '项目'
  if (!await msg.confirm(`确定要将《${title}》的所有章节导出为TXT文件吗？`)) return
  try {
    const token = localStorage.getItem('moyu_token')
    const headers: Record<string, string> = {}
    if (token) headers.Authorization = `Bearer ${token}`
    const downloadUrl = api.exportProject(currentProjectId.value!, 'txt') as string
    const res = await fetch(downloadUrl, { headers })
    if (!res.ok) throw new Error(`导出失败：${res.status}`)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${title}.txt`
    a.click()
    URL.revokeObjectURL(url)
    msg.success('导出成功')
  } catch (e: any) {
    msg.error('导出失败：' + formatError(e))
  }
}

// ===== 编辑器打开/关闭 =====
async function openEditor(c: any) {
  editing.value = c
  editingTitle.value = c.title || `第${c.chapter_number}章`
  editingContent.value = ''
  narrativePov.value = ''  // 空 = 按小说设定
  projectDefaultPov.value = projectData.value?.narrative_pov || '第三人称'
  projectDefaultStyleId.value = projectData.value?.writing_style?.style_id

  // 加载章节内容
  const ch = await apiGet<any>(`/api/projects/${currentProjectId.value}/chapters/${c.id}`).catch(() => null)
  if (ch) editingContent.value = ch.content || ''
  rawOutput.value = ch?.raw_output || ''

  // 加载编辑器选项（并行）
  await Promise.all([
    loadWritingStylesIfEmpty(),
    loadSkillsIfEmpty(),
    loadModelsIfEmpty(),
  ])

  editorOpen.value = true
}

async function loadWritingStylesIfEmpty() {
  if (writingStyles.value.length > 0) {
    autoSelectDefaultStyle()
    return
  }
  try {
    writingStyles.value = await fetchWritingStyles()
    autoSelectDefaultStyle()
  } catch {}
}

function autoSelectDefaultStyle() {
  if (writingStyles.value.length === 0) return
  // 1. 项目绑定的风格
  const projectStyleId = projectData.value?.writing_style?.style_id
  if (projectStyleId) {
    const match = writingStyles.value.find((s: any) => s.id === projectStyleId)
    if (match) { selectedStyleId.value = match.id; return }
  }
  // 2. 用户全局默认
  const def = writingStyles.value.find((s: any) => s.is_default)
  if (def) { selectedStyleId.value = def.id; return }
  // 3. 第一个风格兜底
  if (selectedStyleId.value == undefined) {
    selectedStyleId.value = writingStyles.value[0].id
  }
}

async function loadSkillsIfEmpty() {
  if (availableSkills.value.length > 0) return
  try {
    const all = await fetchSkills()
    availableSkills.value = all.filter((s: any) =>
      s.is_enabled !== false &&
      (s.skill_type === 'custom' || s.skill_type === 'mcp')
    )
  } catch {}
}

async function loadModelsIfEmpty() {
  if (availableModels.value.length > 0) return
  try {
    const r = await fetchRemoteModels()
    availableModels.value = r.models
    defaultModelName.value = r.default_model
  } catch {}
}

// ===== AI 创作（异步后台任务）=====
async function onGenerate() {
  if (!editing.value) return
  if (!canGenerateChapter(editing.value)) {
    msg.warning(getGenerateDisabledReason(editing.value))
    return
  }
  generating.value = true
  try {
    const styleObj = selectedStyleId.value ? writingStyles.value.find((s:any) => s.id === selectedStyleId.value) : undefined
    const { task_id } = await api.generateChapterAsync(
      editing.value.id,
      selectedSkillKey.value || undefined,
      styleObj,
      {
        narrative_pov: narrativePov.value || undefined,
        target_word_count: targetWords.value,
        model: selectedModel.value || undefined,
        thinking_mode: skillThinkingMode.value || undefined,
      },
    )
    const { trackTask } = useBackgroundTasks()
    trackTask({ id: task_id, task_type: 'chapter_generate', title: `生成第${editing.value.chapter_number}章` })
	    msg.success('章节生成任务已提交，可在右下角查看进度')
	    if (import.meta.client) localStorage.setItem('moyu_chapter_words', String(targetWords.value))
	    editorOpen.value = false
  } catch (e: any) {
    msg.error('生成失败：' + formatError(e))
  } finally {
    generating.value = false
  }
}

// ===== 保存 =====
async function onSave() {
  if (!editing.value) return
  saving.value = true
  try {
    await api.updateChapter(editing.value.id, {
      title: editingTitle.value,
      content: editingContent.value,
      status: 'completed',
    })
    if (import.meta.client) localStorage.setItem('moyu_chapter_words', String(targetWords.value))
    await refreshList()
    msg.success('保存成功')
  } catch (e: any) {
    msg.error('保存失败：' + formatError(e))
  } finally {
    saving.value = false
  }
}

// ===== 清空 =====
async function clearContent() {
  if (!editing.value) return
  const chNum = editing.value.chapter_number
  const hasSubsequent = (chapters.value || []).some((c: any) => c.chapter_number > chNum && c.content?.trim())
  const cascade = hasSubsequent && await msg.confirm(
    `清空第${chNum}章后，第${chNum + 1}章及之后的章节内容将与新内容不衔接。\n是否一并清空后续章节？`,
    '清空并级联'
  )
  if (!cascade && !await msg.confirm(`确认清空第${chNum}章？`)) return
  try {
    const res = await api.clearChapter(editing.value.id, cascade)
    editingContent.value = ''
    await refreshList()
    if (cascade) {
      msg.success(`已清空第 ${(res.cleared || []).join('、')} 章`)
    }
  } catch (e: any) {
    msg.error('清空失败：' + formatError(e))
  }
}

// ===== 从大纲创建 =====
async function createFromOutline(o: any) {
  try {
    await api.createChapter({ chapter_number: o.chapter_number, title: o.title, outline_id: o.id })
    await refreshList()
    msg.success(`第${o.chapter_number}章已创建`)
  } catch (e: any) {
    msg.error('创建失败：' + formatError(e))
  }
}

const batchCreating = ref(false)
async function createAllFromOutlines() {
  const uncreated = (outlines.value || []).filter((o: any) => !createdChapterNos.value.has(o.chapter_number))
  if (!uncreated.length) { msg.info('没有需要创建的章节'); return }
  batchCreating.value = true
  let created = 0
  try {
    for (const o of uncreated) {
      await api.createChapter({ chapter_number: o.chapter_number, title: o.title, outline_id: o.id })
      created++
    }
    await refreshList()
    msg.success(`已创建 ${created} 个章节`)
  } catch (e: any) {
    msg.error(`创建失败（已完成 ${created}/${uncreated.length}）：` + formatError(e))
  } finally {
    batchCreating.value = false
  }
}

// ===== 手动创建（one-to-many）=====
const manualCreateOpen = ref(false)
const manualCreateNo = ref(1)
const manualCreateTitle = ref('')
const manualCreateOutlineId = ref<number | undefined>()

function openManualCreate() {
  const nextNo = (chapters.value?.length || 0) + 1
  manualCreateNo.value = nextNo
  manualCreateTitle.value = `第 ${nextNo} 章`
  manualCreateOutlineId.value = undefined
  manualCreateOpen.value = true
}

async function onManualCreate() {
  try {
    await api.createChapter({
      chapter_number: manualCreateNo.value,
      title: manualCreateTitle.value,
      outline_id: manualCreateOutlineId.value,
    })
    await refreshList()
    manualCreateOpen.value = false
    msg.success('章节已创建')
  } catch (e: any) {
    msg.error('创建失败：' + formatError(e))
  }
}

// ===== 新建空白章 =====
async function createNewChapter() {
  const nextNo = (chapters.value?.length || 0) + 1
  try {
    await api.createChapter({ chapter_number: nextNo, title: `第 ${nextNo} 章` })
    await refreshList()
    msg.success('已创建')
  } catch (e: any) {
    msg.error('创建失败：' + formatError(e))
  }
}

// ===== 删除 =====
async function onDelete(id: number) {
  if (!await msg.confirm('确认删除？')) return
  try {
    await api.deleteChapter(id)
    await refreshList()
    msg.success('已删除')
  } catch (e: any) {
    msg.error('删除失败：' + formatError(e))
  }
}

// ===== 修改弹窗 =====
function openModify(c: any) {
  modifyChapter.value = c
  modifyTitle.value = c.title || `第${c.chapter_number}章`
  modifyStatus.value = c.status || 'draft'
  modifyOpen.value = true
}

async function onModify() {
  if (!modifyChapter.value) return
  try {
    await api.updateChapter(modifyChapter.value.id, {
      title: modifyTitle.value,
      status: modifyStatus.value,
    })
    await refreshList()
    modifyOpen.value = false
    msg.success('修改成功')
  } catch (e: any) {
    msg.error('修改失败：' + formatError(e))
  }
}

// ===== 重写/局部重写应用后，重新加载章节内容 =====
async function onRewriteApplied() {
  if (!editing.value) return
  try {
    const ch = await apiGet<any>(`/api/projects/${currentProjectId.value}/chapters/${editing.value.id}`).catch(() => null)
    if (ch) {
      editingContent.value = ch.content || ''
      editingTitle.value = ch.title || editingTitle.value
    }
    await refreshList()
    msg.success('章节内容已更新')
  } catch (e: any) {
    msg.error('刷新失败：' + formatError(e))
  }
}

// ===== 去AI味 =====
const showDenoise = ref(false)
const denoiseText = ref('')
const denoiseResult = ref('')
const denoisePreview = ref(false)
const denoising = ref(false)

function openDenoise() {
  const ta = document.querySelector('.ch-editor textarea') as any
  denoiseText.value = (ta && ta.selectionStart !== ta.selectionEnd)
    ? ta.value.substring(ta.selectionStart, ta.selectionEnd)
    : editingContent.value
  denoiseResult.value = ''
  denoisePreview.value = false
  showDenoise.value = true
}

async function onDenoise() {
  if (!denoiseText.value.trim()) return
  denoising.value = true
  try {
    const r = await api.aiDenoising({ text: denoiseText.value })
    denoiseResult.value = r.processed_text || ''
    denoisePreview.value = true
  } catch (e: any) {
    msg.error('失败：' + formatError(e))
  } finally {
    denoising.value = false
  }
}

function applyDenoise() {
  editingContent.value = denoiseResult.value
  showDenoise.value = false
  msg.success('已应用')
}

// ===== 纯阅读 Modal（对标 mumu，沉浸式，无标注） =====
const pureReaderVisible = ref(false)
const pureReaderChapter = ref<any>(null)
const pureReaderLoading = ref(false)

async function fetchChapterForReader(id: number): Promise<any> {
  return await apiGet<any>(`/api/projects/${currentProjectId.value}/chapters/${id}`)
}

// 全屏沉浸式阅读：打开纯阅读 Modal
async function goReader(c: any) {
  // 章节列表中的 c 通常不含 content，先取完整内容
  if (c.content) {
    pureReaderChapter.value = c
  } else {
    pureReaderLoading.value = true
    pureReaderChapter.value = c  // 先显示标题
    pureReaderVisible.value = true
    try {
      const ch = await fetchChapterForReader(c.id)
      pureReaderChapter.value = { ...c, content: ch.content, word_count: ch.word_count }
    } catch (e: any) {
      msg.error('加载章节内容失败：' + formatError(e))
    } finally {
      pureReaderLoading.value = false
      return
    }
  }
  pureReaderVisible.value = true
}

async function onPureReaderChange(chapterId: number) {
  pureReaderLoading.value = true
  try {
    const ch = await fetchChapterForReader(chapterId)
    pureReaderChapter.value = ch
  } catch (e: any) {
    msg.error('加载章节失败：' + formatError(e))
  } finally {
    pureReaderLoading.value = false
  }
}

// ===== 内嵌阅读器（带标注）=====
const readerOpen = ref(false)
const readerChapter = ref<any>(null)
const readerAnnotations = ref<any[]>([])
const readerSummary = ref<any>({})
const readerLoading = ref(false)
const readerActiveAnn = ref<any>(null)
const readerShowSidebar = ref(true)

const readerTypeMeta: Record<string, { label: string; color: string; icon: string }> = {
  hook: { label: '剧情钩子', color: '#C75B5B', icon: '🎣' },
  foreshadow: { label: '伏笔', color: '#1677FF', icon: '🔮' },
  plot_point: { label: '关键情节', color: '#52A569', icon: '⭐' },
  character_event: { label: '角色事件', color: '#D49A4E', icon: '👤' },
}

const readerGroups = computed(() => {
  const groups: Record<string, any[]> = { hook: [], foreshadow: [], plot_point: [], character_event: [] }
  for (const a of (readerAnnotations.value || [])) {
    if (a && a.type && groups[a.type]) groups[a.type].push(a)
  }
  return (Object.keys(readerTypeMeta) as string[])
    .map(type => ({
      type,
      label: readerTypeMeta[type].label,
      icon: readerTypeMeta[type].icon,
      color: readerTypeMeta[type].color,
      items: groups[type],
    }))
    .filter(g => g.items.length > 0)
})

async function openReader(c: any) {
  readerOpen.value = true
  readerLoading.value = true
  readerActiveAnn.value = null
  readerAnnotations.value = []
  readerSummary.value = {}
  try {
    const ch = await apiGet<any>(`/api/projects/${currentProjectId.value}/chapters/${c.id}`)
    readerChapter.value = ch
    const r = await api.getAnnotations(c.id)
    readerAnnotations.value = r.annotations || []
    readerSummary.value = r.summary || {}
  } catch (e: any) {
    msg.error('加载失败：' + formatError(e))
  } finally {
    readerLoading.value = false
  }
}
	
async function readerNavigate(direction: -1 | 1) {
  const list = chapters.value || []
  const idx = list.findIndex((c: any) => c.id === readerChapter.value?.id)
  const next = list[idx + direction]
  if (next) await openReader(next)
}

function readerNavInfo() {
  const list = chapters.value || []
  const idx = list.findIndex((c: any) => c.id === readerChapter.value?.id)
  return { hasPrev: idx > 0, hasNext: idx < list.length - 1 }
}

const readerAnalyzing = ref(false)
async function readerAnalyze() {
  if (!readerChapter.value) return
  readerAnalyzing.value = true
  try {
    const r = await api.triggerAnalysisAsync(readerChapter.value.id)
    if (r?.task_id) {
      trackBgTask({ id: r.task_id, task_type: 'chapter_analyze', title: `分析第${readerChapter.value.chapter_number}章`, status: 'pending' })
      msg.success('分析任务已提交，可在右下角查看进度')
      // 后台轮询，完成后刷新阅读器标注
      pollReaderAnalysis(r.task_id)
    } else {
      msg.info('该章节已在分析中或无需分析')
    }
  } catch (e: any) {
    msg.error('提交分析失败：' + formatError(e))
  } finally {
    readerAnalyzing.value = false
  }
}

async function pollReaderAnalysis(taskId: number) {
  const maxAttempts = 300
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(r => setTimeout(r, 2000))
    try {
      const t = await apiGet<any>(`/api/tasks/${taskId}`)
      if (t.status === 'completed') {
        if (readerChapter.value) {
          const r = await api.getAnnotations(readerChapter.value.id)
          readerAnnotations.value = r.annotations || []
          readerSummary.value = r.summary || {}
        }
        msg.success('分析完成，标注已更新')
        await refreshList()
        return
      }
      if (t.status === 'failed' || t.status === 'cancelled') {
        msg.error('分析失败：' + (t.error || ''))
        return
      }
    } catch { /* 忽略单次轮询错误 */ }
  }
}

// ===== 章节规划（ExpansionPlan）=====
const planEditorOpen = ref(false)
const planViewOpen = ref(false)
const planEditingChapter = ref<any>(null)
const planCurrent = ref<any>(null)        // 当前规划数据（编辑/查看用）
const planSummary = ref<string>('')        // 章节摘要

// 打开规划编辑（先拉取单章详情拿完整 expansion_plan）
async function openPlanEditor(c: any) {
  planEditingChapter.value = c
  try {
    const detail = await apiGet<any>(`/api/projects/${currentProjectId.value}/chapters/${c.id}`)
    planCurrent.value = detail?.expansion_plan || null
    planSummary.value = detail?.summary || ''
  } catch {
    planCurrent.value = null
    planSummary.value = ''
  }
  planEditorOpen.value = true
}

// 打开规划查看
async function openPlanView(c: any) {
  planEditingChapter.value = c
  try {
    const detail = await apiGet<any>(`/api/projects/${currentProjectId.value}/chapters/${c.id}`)
    planCurrent.value = detail?.expansion_plan || null
    planSummary.value = detail?.summary || ''
  } catch {
    planCurrent.value = null
    planSummary.value = ''
  }
  planViewOpen.value = true
}

// 规划保存成功后刷新列表（更新 has_expansion_plan 标记）
async function onPlanSaved() {
  await refreshList()
}
</script>

<template>
  <div class="ch-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="page-header-left">
        <h2 class="page-title">📖 章节管理</h2>
        <a-tag :color="outlineMode === 'one_to_one' ? 'blue' : 'green'" style="width: fit-content">
          {{ outlineMode === 'one_to_one' ? '传统模式：章节由大纲管理' : '细化模式：章节可在大纲页面展开' }}
        </a-tag>
      </div>
      <div class="page-header-right">
        <a-input-search
          v-model:value="searchKeyword"
          placeholder="搜索章节（序号/标题/大纲）"
          allow-clear
          style="width: 240px"
        />
        <a-button v-if="outlineMode === 'one_to_many'" @click="openManualCreate">
          + 手动创建
        </a-button>
        <a-button
          :loading="batchAnalyzing"
          :disabled="!chapters?.length || batchAnalyzableCount === 0"
          style="color: #D49A4E; border-color: #D49A4E"
          @click="onBatchAnalyze"
        >
          ⚡ 一键分析{{ batchAnalyzableCount > 0 ? ` (${batchAnalyzableCount})` : '' }}
        </a-button>
        <a-popconfirm title="清理重复的分析记录（每个章节只保留最新一份）" @confirm="onCleanupAnalyses">
          <a-button :loading="cleaningUp" style="font-size:12px">🧹 清理旧分析</a-button>
        </a-popconfirm>
        <BatchGeneratePanel :chapters="chapters || []" @done="refreshList" />
        <a-button :disabled="!chapters?.length" @click="onExportTxt">📥 导出TXT</a-button>
      </div>
    </div>

    <!-- 从大纲创建（仅 1对1 模式；1对多模式下章节由大纲页面"展开为多章"产生，不在此建空壳） -->
    <a-card
      v-if="outlineMode === 'one_to_one' && outlines && outlines.filter((o: any) => !createdChapterNos.has(o.chapter_number)).length"
      size="small"
      title="从大纲创建章节"
      style="margin-bottom: 12px"
    >
      <div class="outline-chips">
        <a-button
          v-for="o in outlines.filter((o: any) => !createdChapterNos.has(o.chapter_number))"
          :key="o.id"
          size="small"
          @click="createFromOutline(o)"
        >
          第{{ o.chapter_number }}章 {{ o.title }}
        </a-button>
      </div>
      <a-button type="primary" size="small" style="margin-top:8px;" :loading="batchCreating" @click="createAllFromOutlines">
        📦 一键全部创建
      </a-button>
    </a-card>

    <!-- ===== 章节列表 ===== -->
    <template v-if="sortedChapters.length">
      <!-- one-to-many 按大纲分组显示（仅当有多个分组时） -->
      <a-collapse v-if="outlineMode === 'one_to_many'" :default-active-key="pagedGroupedChapters.length > 0 ? ['0'] : []" style="background: transparent">
        <a-collapse-panel
          v-for="(group, gi) in pagedGroupedChapters"
          :key="String(gi)"
          :style="{ marginBottom: '12px', background: '#fff', borderRadius: '8px', border: '1px solid #E8E4DC' }"
        >
          <template #header>
            <div class="group-header">
              <a-tag :color="group.outlineId ? 'blue' : 'default'" style="margin: 0">
                {{ group.outlineId ? `📖 大纲 ${group.outlineOrder}` : '📝 未分类' }}
              </a-tag>
              <span class="group-title">{{ group.outlineTitle }}</span>
              <a-tag color="success" size="small">{{ group.chapters.length }} 章</a-tag>
              <a-tag color="processing" size="small">
                {{ group.chapters.reduce((s: number, c: any) => s + (c.word_count || 0), 0).toLocaleString() }} 字
              </a-tag>
            </div>
          </template>
          <div class="ch-list">
            <div v-for="c in group.chapters" :key="c.id" class="ch-row">
              <div class="ch-row-icon">📄</div>
              <div class="ch-row-main">
                <div class="ch-row-head">
                  <span class="ch-row-title">第{{ c.chapter_number }}章：{{ c.title || '无标题' }}</span>
                  <a-tag :color="statusColor(c.status)" size="small">{{ statusText(c.status) }}</a-tag>
                  <a-tag v-if="c.word_count" color="success" size="small">{{ (c.word_count || 0).toLocaleString() }}字</a-tag>
                  <a-tag v-if="c.word_count >= 50 && c.analyzed" color="cyan" size="small">📊 已分析</a-tag>
                  <a-tag v-if="c.word_count >= 50 && !c.analyzed" color="orange" size="small">⏳ 待分析</a-tag>
                  <a-tooltip v-if="outlineMode === 'one_to_many' && c.has_expansion_plan" title="查看规划">
                    <a-button type="text" size="small" style="padding:0 3px;font-size:13px;color:#1677ff;min-width:auto;height:auto;line-height:1" @click.stop="openPlanView(c)">◉</a-button>
                  </a-tooltip>
                  <a-tooltip v-if="outlineMode === 'one_to_many'" title="编辑规划">
                    <a-button type="text" size="small" style="padding:0 3px;font-size:13px;color:#8C8C8C;min-width:auto;height:auto;line-height:1" @click.stop="openPlanEditor(c)">✎</a-button>
                  </a-tooltip>
                  <a-tooltip v-if="!canGenerateChapter(c)" :title="getGenerateDisabledReason(c)">
                    <a-tag color="warning" size="small">🔒 {{ getGenerateDisabledReason(c).includes('分析') ? '需先分析前章' : '需前置章节' }}</a-tag>
                  </a-tooltip>
                </div>
                <div v-if="c.content_preview" class="ch-row-preview">{{ c.content_preview }}{{ c.word_count > 150 ? '…' : '' }}</div>
                <div v-else-if="c.summary" class="ch-row-summary">{{ c.summary.substring(0, 100) }}</div>
              </div>
              <div class="ch-row-actions" @click.stop>
                <a-button type="text" size="small" :disabled="!c.word_count" @click.stop="goReader(c)">📖 阅读</a-button>
                <a-button type="text" size="small" @click="openEditor(c)">编辑</a-button>
                <a-button type="text" size="small" @click.stop="openAnalysis(c)">📊 分析</a-button>
                <a-button type="text" size="small" @click.stop="openModify(c)">⚙️ 修改</a-button>
                <a-popconfirm title="确认删除该章节？" @confirm="onDelete(c.id)">
                  <a-button type="text" size="small" danger @click.stop>🗑️ 删除</a-button>
                </a-popconfirm>
              </div>
            </div>
          </div>
        </a-collapse-panel>
      </a-collapse>

      <!-- 默认扁平列表 -->
      <div v-else class="ch-list">
        <div v-for="c in pagedChapters" :key="c.id" class="ch-row">
          <div class="ch-row-icon">📄</div>
          <div class="ch-row-main">
            <div class="ch-row-head">
              <span class="ch-row-title">第{{ c.chapter_number }}章：{{ c.title || '无标题' }}</span>
              <a-tag :color="statusColor(c.status)" size="small">{{ statusText(c.status) }}</a-tag>
              <a-tag v-if="c.word_count" color="success" size="small">{{ (c.word_count || 0).toLocaleString() }}字</a-tag>
              <a-tag v-if="c.has_expansion_plan" color="purple" size="small">📋 已规划</a-tag>
              <a-tag v-if="c.word_count >= 50 && c.analyzed" color="cyan" size="small">📊 已分析</a-tag>
              <a-tag v-if="c.word_count >= 50 && !c.analyzed" color="orange" size="small">⏳ 待分析</a-tag>
              <a-tooltip v-if="outlineMode === 'one_to_many' && c.has_expansion_plan" title="查看规划">
                <a-button type="text" size="small" style="padding:0 3px;font-size:13px;color:#1677ff;min-width:auto;height:auto;line-height:1" @click.stop="openPlanView(c)">◉</a-button>
              </a-tooltip>
              <a-tooltip v-if="outlineMode === 'one_to_many'" title="编辑规划">
                <a-button type="text" size="small" style="padding:0 3px;font-size:13px;color:#8C8C8C;min-width:auto;height:auto;line-height:1" @click.stop="openPlanEditor(c)">✎</a-button>
              </a-tooltip>
              <a-tag v-if="c.quality_alert?.includes('consistency_issue')" color="red" size="small">⚠️矛盾</a-tag>
              <a-tag v-if="c.quality_alert?.includes('low_score')" color="orange" size="small">低分</a-tag>
              <a-tag v-if="c.quality_score" color="processing" size="small">评分{{ c.quality_score }}</a-tag>
              <a-tooltip v-if="!canGenerateChapter(c)" :title="getGenerateDisabledReason(c)">
                <a-tag color="warning" size="small">🔒 {{ getGenerateDisabledReason(c).includes('分析') ? '需先分析前章' : '需前置章节' }}</a-tag>
              </a-tooltip>
            </div>
            <div v-if="c.content_preview" class="ch-row-preview">{{ c.content_preview }}{{ c.word_count > 150 ? '…' : '' }}</div>
            <div v-else-if="c.summary" class="ch-row-summary">{{ c.summary.substring(0, 100) }}</div>
            <div v-else-if="!c.word_count" class="ch-row-empty">暂无内容</div>
          </div>
          <div class="ch-row-actions" @click.stop>
            <a-button type="text" size="small" :disabled="!c.word_count" @click.stop="goReader(c)">📖 阅读</a-button>
            <a-button type="text" size="small" @click="openEditor(c)">编辑</a-button>
            <a-button type="text" size="small" @click.stop="openAnalysis(c)">📊 分析</a-button>
            <a-button type="text" size="small" @click.stop="openModify(c)">⚙️ 修改</a-button>
          </div>
        </div>
      </div>
    </template>

    <a-empty v-else description="暂无章节" />

    <!-- 分页 -->
    <div v-if="sortedChapters.length > pageSize" class="pagination-bar">
      <a-pagination
        v-model:current="currentPage"
        v-model:page-size="pageSize"
        :total="sortedChapters.length"
        :page-size-options="pageSizeOptions"
        show-size-changer
        :show-total="(t: number) => `共 ${t} 章`"
        size="small"
      />
    </div>

    <!-- ===== 编辑器弹窗 ===== -->
    <a-modal
      v-model:open="editorOpen"
      :title="`编辑：第${editing?.chapter_number}章`"
      width="90%"
      :style="{ top: '10px' }"
      :footer="null"
      :destroy-on-close="true"
    >
      <div v-if="editing" class="editor">
        <!-- 标题 + 操作按钮 -->
        <div class="editor-bar">
          <a-input v-model:value="editingTitle" size="large" style="flex: 1; font-weight: 600; font-family: 'Noto Serif SC', serif;" />
          <a-button
            type="primary"
            :loading="generating"
            :disabled="!canGenerateChapter(editing)"
            :title="!canGenerateChapter(editing) ? getGenerateDisabledReason(editing) : ''"
            @click="onGenerate"
          >
            {{ generating ? 'AI创作中…' : '⚡ AI创作' }}
          </a-button>
          <ClientOnly>
            <ChapterRewritePanel :chapter-id="editing.id" :chapter-content="editingContent" @applied="onRewriteApplied" />
            <template #fallback><a-button disabled>✏️ 重写/润色</a-button></template>
          </ClientOnly>
          <a-button :loading="denoising" @click="openDenoise">去AI味</a-button>
          <a-button type="primary" :loading="saving" @click="onSave">💾 保存</a-button>
          <a-button @click="clearContent">清空</a-button>
        </div>

        <!-- 创作设置 -->
        <div class="editor-settings">
          <div class="settings-row">
            <span class="settings-label">🎨 风格</span>
            <a-select v-model:value="selectedStyleId" size="small" style="width: 160px" placeholder="项目默认" allow-clear>
              <a-select-option v-for="s in writingStyles" :key="s.id" :value="s.id">{{ s.name }}{{ s.id === projectDefaultStyleId ? ' ★' : '' }}</a-select-option>
            </a-select>
          </div>
          <div class="settings-row">
            <span class="settings-label">👁️ 视角</span>
            <a-select v-model:value="narrativePov" size="small" style="width: 140px" allow-clear>
              <a-select-option :value="''">默认（{{ projectDefaultPov }}）</a-select-option>
              <a-select-option value="第三人称">第三人称</a-select-option>
              <a-select-option value="第一人称">第一人称</a-select-option>
              <a-select-option value="全知视角">全知视角</a-select-option>
            </a-select>
          </div>
          <div class="settings-row">
            <span class="settings-label">📏 字数</span>
            <a-input-number v-model:value="targetWords" :min="500" :max="10000" :step="100" size="small" style="width: 110px" />
          </div>
          <div class="settings-row">
            <span class="settings-label">🧩 Skill</span>
            <a-select v-model:value="selectedSkillKey" size="small" style="width: 150px" placeholder="不注入" allow-clear>
              <a-select-option v-for="s in availableSkills" :key="s.name || s.template_key" :value="s.name || s.template_key">
                {{ s.display_name || s.template_name || s.name }}
              </a-select-option>
            </a-select>
          </div>
          <div class="settings-row">
            <span class="settings-label">🤖 模型</span>
            <a-select v-model:value="selectedModel" size="small" style="width: 180px" allow-clear>
              <a-select-option :value="''">{{ defaultModelName ? `默认（${defaultModelName}）` : '使用默认模型' }}</a-select-option>
              <a-select-option v-for="m in availableModels" :key="m.value" :value="m.value">{{ m.label }}</a-select-option>
            </a-select>
          </div>
          <div class="settings-row">
            <span class="settings-label">🧠 思考</span>
            <a-select v-model:value="skillThinkingMode" size="small" style="width: 120px" allow-clear>
              <a-select-option :value="''">默认</a-select-option>
              <a-select-option value="none">关闭</a-select-option>
              <a-select-option value="low">浅思考</a-select-option>
              <a-select-option value="medium">深思考</a-select-option>
              <a-select-option value="high">深度思考</a-select-option>
            </a-select>
          </div>
        </div>

        <!-- RAW 原始输出对比（弹窗） -->
        <div v-if="rawOutput" style="margin-bottom:8px">
          <a-button size="small" type="link" @click="showRaw = true" style="padding:0">
            📄 查看清理前后对比
          </a-button>
        </div>
        <ContentComparisonModal
          v-model:visible="showRaw"
          title="清理前后对比"
          :original-content="rawOutput"
          :new-content="editingContent"
        />

        <!-- 内容编辑区 -->
        <div class="ch-editor">
          <a-textarea v-model:value="editingContent" :rows="18" :disabled="generating" placeholder="点击AI创作生成正文..." />
        </div>
        <div class="editor-foot">
          <span>字数：{{ editingContent.length.toLocaleString() }}</span>
        </div>
      </div>
    </a-modal>

    <!-- ===== 重写对比弹窗（分析建议 → 重写 → 对比） ===== -->
    <ContentComparisonModal
      v-model:visible="rewriteCompareOpen"
      title="重写前后对比"
      :original-content="rewriteOriginal"
      :new-content="rewriteNew"
      show-actions
      @apply="onApplyRewriteCompare"
    />

    <!-- ===== 修改弹窗 ===== -->
    <a-modal v-model:open="modifyOpen" title="修改章节信息" width="480px">
      <a-form :label-col="{ span: 5 }">
        <a-form-item label="章节标题">
          <a-input v-model:value="modifyTitle" />
        </a-form-item>
        <a-form-item label="章节序号">
          <a-input-number :value="modifyChapter?.chapter_number" disabled style="width: 100%" />
        </a-form-item>
        <a-form-item label="状态">
          <a-select v-model:value="modifyStatus">
            <a-select-option value="draft">草稿</a-select-option>
            <a-select-option value="completed">已完成</a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
      <template #footer>
        <a-button @click="modifyOpen = false">取消</a-button>
        <a-button type="primary" @click="onModify">保存</a-button>
      </template>
    </a-modal>

    <!-- ===== 手动创建弹窗（one-to-many） ===== -->
    <a-modal v-model:open="manualCreateOpen" title="手动创建章节" width="480px">
      <a-form :label-col="{ span: 5 }">
        <a-form-item label="章节序号">
          <a-input-number v-model:value="manualCreateNo" :min="1" style="width: 100%" />
        </a-form-item>
        <a-form-item label="章节标题">
          <a-input v-model:value="manualCreateTitle" />
        </a-form-item>
        <a-form-item label="关联大纲">
          <a-select v-model:value="manualCreateOutlineId" placeholder="选择大纲" allow-clear style="width: 100%">
            <a-select-option v-for="o in (outlines || [])" :key="o.id" :value="o.id">
              第{{ o.chapter_number }}章 {{ o.title }}
            </a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
      <template #footer>
        <a-button @click="manualCreateOpen = false">取消</a-button>
        <a-button type="primary" @click="onManualCreate">创建</a-button>
      </template>
    </a-modal>

    <!-- ===== 去AI味弹窗 ===== -->
    <a-modal v-model:open="showDenoise" title="去AI味" width="600px">
      <div v-if="!denoisePreview">
        <a-textarea v-model:value="denoiseText" :rows="6" />
      </div>
      <div v-else>
        <strong style="color: #4D8088">结果</strong>
        <div style="background: #F0F5F5; padding: 8px; border-radius: 6px; margin-top: 4px; white-space: pre-wrap">{{ denoiseResult }}</div>
      </div>
      <template #footer>
        <a-button @click="showDenoise = false">{{ denoisePreview ? '关闭' : '取消' }}</a-button>
        <a-button v-if="denoisePreview" type="primary" @click="applyDenoise">应用</a-button>
        <a-button v-else type="primary" :loading="denoising" @click="onDenoise">润色</a-button>
      </template>
    </a-modal>

    <!-- ===== 内嵌阅读器（带标注） ===== -->
    <a-modal
      v-model:open="readerOpen"
      :width="1100"
      :title="readerChapter ? `📖 阅读：第${readerChapter.chapter_number}章 · ${readerChapter.title}` : '阅读'"
      :style="{ top: '10px' }"
      :footer="null"
      :destroy-on-close="true"
    >
      <div v-if="readerLoading" style="text-align: center; padding: 60px; color: #8C8C8C">加载中…</div>
      <div v-else-if="readerChapter" class="reader-layout">
        <div class="reader-main">
          <div class="reader-toolbar-bar">
            <a-button size="small" :disabled="!readerNavInfo().hasPrev" @click="readerNavigate(-1)">← 上一章</a-button>
            <a-button size="small" type="link" @click="readerShowSidebar = !readerShowSidebar">
              {{ readerShowSidebar ? '隐藏标注' : '显示标注' }}
            </a-button>
            <a-button size="small" :loading="readerAnalyzing" @click="readerAnalyze">
              🤖 {{ readerAnalyzing ? '提交中…' : (readerSummary.has_analysis ? '重新分析' : '分析此章') }}
            </a-button>
            <a-button size="small" :disabled="!readerNavInfo().hasNext" style="margin-left: auto" @click="readerNavigate(1)">
              下一章 →
            </a-button>
          </div>
          <ClientOnly>
            <div class="reader-content-box">
              <AnnotatedText
                :content="readerChapter.content || ''"
                :annotations="readerAnnotations"
                @select="(a: any) => readerActiveAnn = a"
              />
            </div>
          </ClientOnly>
        </div>
        <div v-if="readerShowSidebar" class="reader-side">
          <div class="reader-side-title">
            <span>本章标注</span>
            <span v-if="readerSummary.total" class="reader-side-count">{{ readerSummary.total }}</span>
          </div>
          <div v-if="readerSummary.total" class="reader-side-stats">
            <span v-for="g in readerGroups" :key="'s' + g.type" :style="{ color: g.color }">
              {{ g.icon }} {{ g.items.length }}
            </span>
          </div>
          <div v-for="g in readerGroups" :key="g.type" class="reader-side-group">
            <div class="reader-group-title" :style="{ color: g.color }">
              {{ g.icon }} {{ g.label }}（{{ g.items.length }}）
            </div>
            <div
              v-for="(a, i) in g.items"
              :key="i"
              class="reader-ann-item"
              :class="{ active: readerActiveAnn === a }"
              :style="{ borderLeftColor: g.color }"
              @click="readerActiveAnn = a"
            >
              <div class="reader-ann-title">{{ a.title }}</div>
              <div class="reader-ann-content">{{ a.content }}</div>
            </div>
          </div>
          <div v-if="!readerSummary.total" class="reader-no-annot">
            无标注{{ readerSummary.has_analysis === false ? '（此章节尚未分析）' : '' }}
          </div>
        </div>
      </div>
    </a-modal>

    <!-- ===== 章节分析面板 ===== -->
    <ChapterAnalysisPanel
      v-if="analysisPanelChapter"
      ref="analysisPanelRef"
      :chapter-id="analysisPanelChapter.id"
      :chapter-number="analysisPanelChapter.chapter_number"
      :quality-score="analysisPanelChapter.quality_score"
      @rewrite-with-suggestions="onRewriteWithSuggestions"
    />

    <!-- ===== 章节规划编辑器 ===== -->
    <LazyExpansionPlanEditor
      v-if="planEditingChapter"
      v-model:open="planEditorOpen"
      :chapter-id="planEditingChapter.id"
      :chapter-number="planEditingChapter.chapter_number"
      :chapter-title="planEditingChapter.title"
      :plan-data="planCurrent"
      :chapter-summary="planSummary"
      :outline-id="planEditingChapter.outline_id"
      @saved="onPlanSaved"
    />

    <!-- ===== 章节规划查看 ===== -->
    <LazyExpansionPlanView
      v-if="planEditingChapter"
      v-model:open="planViewOpen"
      :chapter-number="planEditingChapter.chapter_number"
      :chapter-title="planEditingChapter.title"
      :plan="planCurrent"
      :chapter-summary="planSummary"
    />
  </div>

  <!-- 纯阅读 Modal（沉浸式，无标注/分析） -->
  <ChapterReaderModal
    :visible="pureReaderVisible"
    :chapter="pureReaderChapter"
    :chapters="chapters || []"
    :loading="pureReaderLoading"
    @close="pureReaderVisible = false; pureReaderLoading = false"
    @change="onPureReaderChange"
  />
</template>

<style scoped>
.ch-page { display: flex; flex-direction: column; gap: 18px; padding: 4px 0 24px; }

/* 页面头部 */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
  padding: 18px 0;
  border-bottom: 1px solid #E8E4DC;
  position: sticky;
  top: 0;
  z-index: 10;
  background: #FAFAF7;
}
.page-header-left { display: flex; align-items: center; gap: 14px; }
.page-header-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.page-title { margin: 0; font-size: 22px; font-weight: 700; }

/* 大纲 chips */
.outline-chips { display: flex; flex-wrap: wrap; gap: 8px; }

/* 分组头部 */
.group-header { display: flex; align-items: center; gap: 10px; margin-top: 4px; }
.group-title { font-size: 16px; font-weight: 700; }

/* 分页 */
.pagination-bar { display: flex; justify-content: center; padding: 12px 0 4px; }

/* 章节列表 */
.ch-list { display: flex; flex-direction: column; gap: 12px; }
.ch-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 18px 20px;
  background: #fff;
  border: 1px solid #E8E4DC;
  border-left: 3px solid transparent;
  border-radius: 10px;
  cursor: pointer;
  transition: all .2s;
}
.ch-row:hover { border-color: #B8CDD1; border-left-color: #4D8088; box-shadow: 0 4px 12px rgba(43, 43, 43, 0.07); }
.ch-row-icon { font-size: 22px; flex-shrink: 0; margin-top: 2px; }
.ch-row-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.ch-row-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ch-row-title { font-size: 15px; font-weight: 600; }
.ch-row-preview {
  font-size: 13px;
  color: #595959;
  line-height: 1.7;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.ch-row-summary { font-size: 13px; color: #8C8C8C; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; line-height: 1.5; }
.ch-row-empty { font-size: 13px; color: #B5C7CB; }
.ch-row-actions { display: flex; gap: 2px; flex-shrink: 0; align-items: center; }

/* 编辑器 */
.editor { display: flex; flex-direction: column; gap: 12px; }
.editor-bar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.editor-settings {
  display: flex; flex-wrap: wrap; gap: 16px 24px;
  padding: 14px 16px;
  background: #f7f6f2; border-radius: 10px; border: 1px solid #ebe7df;
}
.settings-row { display: flex; flex-direction: column; gap: 4px; }
.settings-label { font-size: 12px; color: #8C8C8C; font-weight: 500; }
.editor-opts { display: flex; gap: 20px; font-size: 13px; color: #595959; flex-wrap: wrap; }
.editor-foot { font-size: 12px; color: #8C8C8C; text-align: right; }
.ch-editor textarea { font-family: 'Noto Serif SC', serif; font-size: 15px; line-height: 2; }
.raw-output-panel { max-height:300px; overflow:auto; background:#fffbe6; border:1px solid #ffe58f; border-radius:6px; padding:12px; font-size:13px; white-space:pre-wrap; color:#8c6d1f; margin-top:4px; }
.diff-added { background:#d4edda; color:#155724; padding:0 2px; border-radius:2px; }
.diff-removed { background:#f8d7da; color:#721c24; text-decoration:line-through; padding:0 2px; border-radius:2px; }
.diff-split { display: flex; gap: 0; margin-top: 8px; border: 1px solid #ebe7df; border-radius: 8px; overflow: hidden; }
.diff-side { flex: 1; overflow-y: auto; max-height: 350px; }
.diff-side-left { background: #fff5f5; }
.diff-side-right { background: #f0fff4; }
.diff-side-title { font-size: 12px; font-weight: 600; padding: 6px 12px; border-bottom: 1px solid #ebe7df; color: #595959; position: sticky; top: 0; background: #faf9f6; z-index: 1; }
.diff-side-content { padding: 10px 14px; font-size: 13px; line-height: 1.9; white-space: pre-wrap; word-break: break-all; }
.diff-divider { width: 1px; background: #ebe7df; flex-shrink: 0; }

/* 阅读器 */
.reader-layout { display: grid; grid-template-columns: 1fr 280px; gap: 14px; height: calc(100vh - 160px); }
.reader-main { display: flex; flex-direction: column; gap: 10px; overflow: hidden; }
.reader-toolbar-bar { display: flex; align-items: center; gap: 8px; }
.reader-content-box { background: #fff; border-radius: 8px; padding: 24px 32px; overflow-y: auto; flex: 1; border: 1px solid #E8E4DC; font-size: 15px; line-height: 2; }
.reader-side { background: #fff; border-radius: 8px; padding: 12px; overflow-y: auto; border: 1px solid #E8E4DC; }
.reader-side-title { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; color: #4D8088; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid #F0EDE6; }
.reader-side-count { background: #4D8088; color: #fff; font-size: 11px; padding: 1px 7px; border-radius: 10px; }
.reader-side-stats { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; font-size: 12px; font-weight: 600; }
.reader-side-group { margin-bottom: 12px; }
.reader-group-title { font-size: 12px; font-weight: 600; margin-bottom: 6px; }
.reader-ann-item { padding: 8px 10px; background: #FAFAF7; border-radius: 6px; border-left: 3px solid #B5C7CB; margin-bottom: 6px; cursor: pointer; }
.reader-ann-item:hover { background: #F0EDE6; }
.reader-ann-item.active { background: #EAF0F1; }
.reader-ann-title { font-size: 12px; font-weight: 600; color: #2B2B2B; margin-bottom: 3px; }
.reader-ann-content { font-size: 12px; color: #595959; line-height: 1.5; }
.reader-no-annot { font-size: 13px; color: #8C8C8C; text-align: center; padding: 24px 0; }
</style>
