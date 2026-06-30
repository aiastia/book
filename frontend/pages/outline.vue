<script setup lang="ts">
import { API } from '~/composables/api'
import { useProject } from '~/composables/useProject'
import { reactive } from 'vue'
import type { Character, Outline, OutlineListResponse, Project } from '~/composables/api/types'
useHead({ title: '故事大纲 — 墨语' })
const { currentProjectId } = useProject()
if (!currentProjectId.value) await navigateTo('/books')
const msg = useMessage()
const route = useRoute()
const router = useRouter()

// 从 URL 读取分页参数
const pageSize = ref(Number(route.query.pageSize || 10))
const currentPage = ref(Number(route.query.page || 1))
const outlineTotal = ref(0)

// 同步分页参数到 URL（仅客户端）
watch([currentPage, pageSize], () => {
  if (process.client) {
    router.replace({
      query: {
        ...route.query,
        page: currentPage.value,
        pageSize: pageSize.value,
      }
    })
  }
})

const { data: outlineData, refresh: refreshOutlines } = await useFetch<OutlineListResponse>(() => {
  const query = `limit=${pageSize.value}&offset=${(currentPage.value - 1) * pageSize.value}`
  return `${useRuntimeConfig().public.apiBase}/api/projects/${currentProjectId.value}/outlines?${query}`
}, {
  onResponse({ response }) {
    const data = response._data
    if (data?.total != null) outlineTotal.value = data.total
  }
})
const outlines = computed<Outline[]>(() => outlineData.value?.items || [])
// total 从响应数据直接派生，避免 onResponse 初始化时机问题导致刷新后丢失分页
watchEffect(() => {
  if (outlineData.value?.total != null) outlineTotal.value = outlineData.value.total
})

const generating = ref(false)
const genCount = ref(10)
const showGen = ref(false)

// 手动创建大纲
const showManualCreate = ref(false)
const manualForm = reactive({
  chapter_number: 1,
  title: '',
  summary: '',
  emotion: '',
  goal: '',
  key_points_text: '',
})
async function onManualCreate() {
  try {
    const nextChapter = outlines.value && outlines.value.length > 0
      ? Math.max(...outlines.value.map((o: any) => o.chapter_number)) + 1
      : 1
    manualForm.chapter_number = nextChapter
    showManualCreate.value = true
  } catch {}
}
async function submitManualCreate() {
  try {
    await API.outline.create(currentProjectId.value, {
      chapter_number: manualForm.chapter_number,
      title: manualForm.title,
      summary: manualForm.summary,
      emotion: manualForm.emotion,
      goal: manualForm.goal,
      key_points: manualForm.key_points_text.split('\n').filter((s: string) => s.trim()),
      characters: [],
      organizations: [],
      scenes: [],
      structure: {},
    })
    showManualCreate.value = false
    msg.success('大纲已创建')
    await refreshOutlines()
  } catch (e: any) { msg.error('创建失败：' + formatError(e)) }
}

// 待补充物品/地点
const pendingEntities = ref<{ pending_items: any[]; pending_locations: any[]; total: number } | null>(null)
const fillingEntities = ref(false)
const showPendingModal = ref(false)
async function checkPendingEntities() {  try {
    const res = await $fetch(`/api/projects/${currentProjectId.value}/outlines/pending-entities`)
    if ((res as any).total > 0) pendingEntities.value = res as any
    else pendingEntities.value = null
  } catch (_) { pendingEntities.value = null }
}
async function fillPendingEntities() {
  fillingEntities.value = true
  try {
    await $fetch(`/api/projects/${currentProjectId.value}/outlines/generate-pending-entities`, { method: 'POST' })
    pendingEntities.value = null
    showPendingModal.value = false
    msg.success('物品和地点已补充')
  } catch (e: any) { msg.error('补充失败：' + formatError(e)) }
  finally { fillingEntities.value = false }
}
// 页面加载和轮询完成后检查
checkPendingEntities()
const defaultModelName: any = ref('')
// 预加载默认模型名（不阻塞，失败不影响使用）
;(async () => {
  try {
    const models = await API.ai.listModels()
    const def = models.find((m: any) => m.is_default) || models[0]
    if (def?.model) defaultModelName.value = def.model
  } catch {}
})()
const editing = ref<any>(null)
const editForm = reactive({
  title: '', summary: '', emotion: '', goal: '',
  key_points_text: '',
  characters: [] as string[],       // 涉及角色（多选 + 可手输新名）
  organizations: [] as string[],    // 涉及组织（多选 + 可手输新名）
  extraFields: [] as Array<{ key: string; value: string }>,
})
// 角色 / 组织候选列表（供下拉多选）
const characterOptions = ref<Array<{ name: string; role: string; label: string }>>([])
const organizationOptions = ref<Array<{ name: string; org_type: string; label: string }>>([])
async function loadCharacterOptions() {
  try {
    const res = await useFetch<Character[]>(() => `${useRuntimeConfig().public.apiBase}/api/projects/${currentProjectId.value}/characters`)
    const list = (res as any).data || (res as any) || []
    characterOptions.value = list.map(c => ({
      name: c.name,
      role: c.role || '',
      label: c.role ? `${c.name}（${c.role}）` : c.name,
    }))
  } catch (e) { console.warn('加载角色失败', e) }
}
async function loadOrganizationOptions() {
  try {
    const res2 = await API.organization.list(currentProjectId.value)
    const list2 = (res2 as any).data || (res2 as any) || []
    organizationOptions.value = list2.map(o => ({
      name: o.name,
      org_type: o.org_type || '',
      label: o.org_type ? `${o.name}（${o.org_type}）` : o.name,
    }))
  } catch (e) { console.warn('加载组织失败', e) }
}
// 添加自定义额外字段
const newFieldKey = ref('')
function addExtraField() {
  const k = newFieldKey.value.trim()
  if (!k) return
  // 避免重复 & 避开基础字段
  if (BASE_FIELD_KEYS.has(k) || editForm.extraFields.some(f => f.key === k)) {
    msg.warning('该字段已存在')
    return
  }
  editForm.extraFields.push({ key: k, value: '' })
  newFieldKey.value = ''
}
function removeExtraField(idx: number) {
  editForm.extraFields.splice(idx, 1)
}

// 续写弹窗
const showContinue = ref(false)
const continueForm = reactive({
  chapter_count: 5,
  story_direction: '',
  plot_stage: '',
  narrative_pov: '',  // 空 = 按小说设定（项目默认）
  other_requirements: '',
  ai_model: '',       // 空 = 使用默认模型
})
// 续写章节数固定选项
const chapterCountOptions = [5, 10, 20, 40]
// 远程模型列表（动态拉取）
const remoteModels = ref<Array<{ id: string; owned_by: string }>>([])
const loadingModels = ref(false)

// 项目默认叙事视角（用于「按小说设定」placeholder 显示）
const projectDefaultPov = computed(() => project.value?.narrative_pov || '第三人称')

// 新角色检测（大纲续写后）
const showNewChars = ref(false)
const newCharNames = ref<string[]>([])
const generatingChars = ref(false)

const isOneToMany = computed(() => (project.value?.outline_mode || 'one_to_one') === 'one_to_many')
const modeLabel = computed(() => isOneToMany.value ? '细化模式 (1→N)' : '传统模式 (1→1)')
const unitLabel = computed(() => isOneToMany.value ? '卷' : '章')

// （卡片展开/收起详情状态已迁移到 OutlineCard 子组件）

// 展开为多章
const expanding = ref(false)
const showExpand = ref(false)
const expandTarget = ref<any>(null)
const expandCount = ref(3)
const expandStrategy = ref('balanced')  // 展开策略：balanced / climax / detail
const expandMode = ref<'new' | 'replace' | 'append'>('new')  // 展开模式：首次/覆盖/追加
const showPreview = ref(false)
const previewData = ref<any>(null)
// 批量展开
const batchExpanding = ref(false)
const showBatchExpand = ref(false)
const batchCount = ref(3)
// 展开/批量展开都可用时，是否有未展开的大纲（控制「批量展开」按钮显隐）
const hasUnexpanded = computed(() => !!(outlines.value && outlines.value.some((o: any) => !o.has_chapters)))
// 预览弹窗 collapse：默认展开所有章节面板（key 统一用字符串，匹配 ant-design-vue 要求）
const activeTab = ref('')  // 预览 Tab 的 active key

// 额外字段的中文标签映射（AI 生成的英文字段名 → 中文展示名）
const FIELD_LABELS: Record<string, string> = {
  shuang_design: '爽点设计',
  reader_hook: '读者钩子',
  decision_basis: '决策依据',
  obstacle_type: '障碍类型',
  hook_type: '钩子类型',
  chapter_breath: '叙事节奏',
  foreshadow_plant: '伏笔埋设',
  foreshadow_advance: '伏笔推进',
  chapter_advance: '本章推进目标',
  plot_summary: '剧情摘要',
  emotional_tone: '情感基调',
  emotional_arc: '情绪弧线',
  narrative_goal: '叙事目标',
  conflict_type: '冲突类型',
  rhythm_tag: '节奏标签',
  scene_anchor: '场景锚点',
  character_intents: '角色微意图',
  estimated_words: '预估字数',
  new_characters_needed: '需新增角色',
  character: '角色',
  this_chapter_goal: '本章目标',
  immediate_want: '当前欲求',
  info_asymmetry: '信息差',
  shock_level: '震惊层级',
  spectator_layers: '围观分层',
  emotional_rhythm: '情绪节奏',
  protagonist_style: '主角逼格',
}
// 已知基础字段，计算额外字段时排除这些
const BASE_FIELD_KEYS = new Set([
  'chapter_number', 'title', 'summary', 'scenes', 'characters', 'organizations',
  'key_points', 'emotion', 'goal', 'structure', 'id', 'has_chapters', 'chapter_count',
  'sort_order', 'outline_type',
])
function fieldLabel(key: string): string {
  return FIELD_LABELS[key] || key
}
// 将任意值渲染为字符串（数组用顿号拼接，对象转 JSON）
function fieldToText(v: any): string {
  if (v == null) return ''
  if (typeof v === 'string') return v
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  if (Array.isArray(v)) {
    return v.map((x: any) => typeof x === 'object' ? JSON.stringify(x) : String(x)).join('；')
  }
  if (typeof v === 'object') {
    // character_intents 特殊处理
    if (v.character && (v.this_chapter_goal || v.immediate_want)) {
      let line = `【${v.character || '?'}】`
      if (v.this_chapter_goal) line += `目标：${v.this_chapter_goal}`
      if (v.immediate_want) line += `；当前欲求：${v.immediate_want}`
      return line
    }
    // shuang_design 格式化
    const sdParts: string[] = []
    if (v.info_asymmetry) sdParts.push(`信息差：${v.info_asymmetry}`)
    if (v.shock_level) sdParts.push(`震惊层级：${v.shock_level}`)
    if (v.emotional_rhythm) sdParts.push(`情绪节奏：${v.emotional_rhythm}`)
    if (v.protagonist_style) sdParts.push(`主角逼格：${v.protagonist_style}`)
    if (Array.isArray(v.spectator_layers) && v.spectator_layers.length) {
      sdParts.push(`围观分层：${v.spectator_layers.join(' → ')}`)
    }
    if (sdParts.length) return sdParts.join('\n')
    // 通用：中文标签
    const parts = Object.entries(v).map(([k, val]) => `${fieldLabel(k)}：${fieldToText(val)}`)
    return parts.join('\n')
  }
  return String(v)
}
// 节奏标签颜色映射
function rhythmColor(tag: string): string {
  const m: Record<string, string> = { '起': 'blue', '承': 'orange', '小高潮': 'red', '高潮': 'volcano', '转': 'purple', '合': 'green' }
  return m[tag] || 'blue'
}

// 解析 structure（含 scenes/characters/key_events 等额外字段）
function parseStructure(o: any): any {
  if (o.structure && typeof o.structure === 'object') return o.structure
  // 尝试从 JSON 字符串解析
  if (typeof o.structure === 'string') {
    try { return JSON.parse(o.structure) } catch { return {} }
  }
  return {}
}
function getCharacters(o: any): string[] {
  const s = parseStructure(o)
  const chars = o.characters || s.characters || []
  if (Array.isArray(chars)) return chars.map((c: any) => typeof c === 'string' ? c : c.name || '')
  return []
}
function getOrganizations(o: any): string[] {
  const s = parseStructure(o)
  const orgs = s.organizations || o.organizations || []
  if (Array.isArray(orgs)) return orgs.map((x: any) => typeof x === 'string' ? x : x.name || '')
  return []
}
function getScenes(o: any): any[] {
  const s = parseStructure(o)
  return s.scenes || []
}
// 提取 AI 生成的额外字段（排除基础字段）
function getExtraFields(o: any): Array<{ key: string; label: string; value: string }> {
  const s = parseStructure(o)
  const result: Array<{ key: string; label: string; value: string }> = []
  for (const [k, v] of Object.entries(s)) {
    if (BASE_FIELD_KEYS.has(k)) continue
    const text = fieldToText(v)
    if (!text) continue
    result.push({ key: k, label: fieldLabel(k), value: text })
  }
  return result
}

async function onGenerate() {
  generating.value = true
  try {
    const { task_id } = await API.outline.generate(genCount.value)
    const { trackTask } = useBackgroundTasks()
    trackTask({ id: task_id, task_type: 'outline_new', title: `生成${genCount.value}章大纲` })
    showGen.value = false
    msg.success('大纲生成任务已提交，可在右下角查看进度')
  }
  catch (e: any) { msg.error('生成失败：' + formatError(e)) }
  finally { generating.value = false }
}

// 任务完成时自动刷新列表（比 setTimeout 轮询更准）
// onTaskCompleted 用前缀匹配，覆盖 outline_new / outline_continue / outline_expand
const { onTaskCompleted } = useBackgroundTasks()
onTaskCompleted('outline_new', () => { refreshOutlines() })
onTaskCompleted('outline_continue', () => { refreshOutlines() })
onTaskCompleted('outline_expand', () => { refreshOutlines() })

function openContinue() {
  // 检查是否已有大纲
  if (!outlines.value || outlines.value.length === 0) {
    // 没有大纲，打开生成弹窗
    showGen.value = true
  } else {
    // 有大纲，打开续写弹窗
    continueForm.chapter_count = 5
    continueForm.story_direction = ''
    continueForm.plot_stage = ''
    continueForm.narrative_pov = ''   // 空表示按小说设定
    continueForm.other_requirements = ''
    continueForm.ai_model = ''        // 空表示使用默认模型
    showContinue.value = true
    // 动态拉取远程模型列表（异步，不阻塞弹窗）
    loadRemoteModels()
  }
}

async function loadRemoteModels() {
  if (remoteModels.value.length && defaultModelName.value) return  // 已加载过
  loadingModels.value = true
  try {
    const r = await API.ai.fetchDefaultRemoteModels()
    remoteModels.value = r.models || []
    defaultModelName.value = r.default_model || ''
  } catch (e: any) {
    // 拉取失败，从本地配置取默认模型名
    try {
      const models = await API.ai.listModels()
      const def = models.find((m: any) => m.is_default) || models[0]
      if (def?.model) defaultModelName.value = def.model
    } catch {}
  } finally {
    loadingModels.value = false
  }
}

async function onContinue() {
  generating.value = true
  try {
    const params: any = { chapter_count: continueForm.chapter_count }
    if (continueForm.story_direction) params.story_direction = continueForm.story_direction
    if (continueForm.plot_stage) params.plot_stage = continueForm.plot_stage
    if (continueForm.narrative_pov) params.narrative_pov = continueForm.narrative_pov
    if (continueForm.other_requirements) params.other_requirements = continueForm.other_requirements
    if (continueForm.ai_model) params.ai_model = continueForm.ai_model

    const { task_id } = await API.outline.continue(currentProjectId.value, params)
    const { trackTask } = useBackgroundTasks()
    trackTask({ id: task_id, task_type: 'outline_continue', title: `续写${continueForm.chapter_count}章大纲` })
    showContinue.value = false
    msg.success('大纲续写任务已提交，可在右下角查看进度')
  }
  catch (e: any) { msg.error('续写失败：' + formatError(e)) }
  finally { generating.value = false }
}
async function onGenerateNewChars() {
  generatingChars.value = true
  try {
    for (const name of newCharNames.value) {
      const { task_id } = await API.character.generateAsync({ count: 1, requirements: `请生成一个名为「${name}」的角色` })
      const { trackTask } = useBackgroundTasks()
      trackTask({ id: task_id, task_type: 'characters', title: `生成角色「${name}」` })
    }
    msg.success(`${newCharNames.value.length} 个角色生成任务已提交，可在右下角查看进度`)
    showNewChars.value = false
    newCharNames.value = []
  } catch (e: any) { msg.error('角色生成失败：' + formatError(e)) }
  finally { generatingChars.value = false }
}
function openEdit(o: any) {
  editing.value = o
  const chars = getCharacters(o)
  const orgs = getOrganizations(o)
  const s = parseStructure(o)
  // 收集额外字段（排除基础字段）
  const extras: Array<{ key: string; value: string }> = []
  for (const [k, v] of Object.entries(s)) {
    if (BASE_FIELD_KEYS.has(k)) continue
    const text = fieldToText(v)
    if (!text) continue
    extras.push({ key: k, value: text })
  }
  Object.assign(editForm, {
    title: o.title || '',
    summary: o.summary || '',
    emotion: o.emotion || '',
    goal: o.goal || '',
    key_points_text: (o.key_points || []).join('\n'),
    characters: [...chars],
    organizations: [...orgs],
    extraFields: extras,
  })
  newFieldKey.value = ''
  // 异步加载角色/组织候选（供下拉选择）
  loadCharacterOptions()
  loadOrganizationOptions()
}
async function onSave() {
  try {
    // 保留原 structure 数据，不丢数据
    const orig = editing.value
    const origStructure = parseStructure(orig)
    // 把额外字段合并进 structure（覆盖同名字段）
    const extraObj: Record<string, any> = {}
    for (const f of editForm.extraFields) {
      const k = f.key.trim()
      if (k) extraObj[k] = f.value
    }
    await API.outline.update(orig.id, {
      title: editForm.title,
      summary: editForm.summary,
      emotion: editForm.emotion,
      goal: editForm.goal,
      key_points: editForm.key_points_text.split('\n').filter(s => s.trim()),
      characters: [...editForm.characters],
      organizations: [...editForm.organizations],
      scenes: getScenes(orig),  // 保留原 scenes
      structure: {
        ...origStructure,
        title: editForm.title, summary: editForm.summary,
        emotion: editForm.emotion, goal: editForm.goal,
        characters: [...editForm.characters],
        organizations: [...editForm.organizations],
        ...extraObj,
      },
      chapter_number: orig.chapter_number,
    })
    await refreshOutlines(); editing.value = null; msg.success('已保存')
  } catch (e: any) { msg.error('保存失败：' + formatError(e)) }
}
async function onDelete(id: number) {
  const o = (outlines.value || []).find((x: any) => x.id === id)
  const hasChapters = o?.has_chapters
  const hint = hasChapters
    ? `此卷已展开为 ${o.chapter_count} 章正文。\n删除卷大纲将同时删除所有展开的章节及其分析数据，且不可恢复。`
    : '确认删除此大纲？'
  if (!await msg.confirm(hint)) return
  try {
    const res = await API.outline.delete(id)
    await refreshOutlines()
    if (res?.deleted_chapters) {
      msg.success(`已删除（含 ${res.deleted_chapters} 章正文）`)
    } else {
      msg.success('已删除')
    }
  }
  catch (e: any) { msg.error('删除失败：' + formatError(e)) }
}

function openExpand(o: any) {
  // 已展开 → 直接预览
  if (o.has_chapters) { viewExpansion(o); return }

  // 顺序展开校验（同 mumu：放置未展开的卷在前，必须先展开它）
  if (outlines.value && outlines.value.length > 1) {
    const sorted = [...outlines.value].sort((a: any, b: any) => a.chapter_number - b.chapter_number)
    const idx = sorted.findIndex((x: any) => x.id === o.id)
    if (idx > 0) {
      const prevUnExpanded = sorted.slice(0, idx).filter((x: any) => !x.has_chapters)
      if (prevUnExpanded.length) {
        const prev = prevUnExpanded[0]
        msg.warning(`请先展开第${prev.chapter_number}卷《${prev.title}》`)
        return
      }
    }
  }

  expandTarget.value = o
  expandCount.value = 3
  expandMode.value = 'new'
  showExpand.value = true
}
async function doExpand() {
  if (!expandTarget.value) return
  const mode = expandMode.value
  expanding.value = true
  try {
    const { task_id } = await API.outline.expand(expandTarget.value.id, expandCount.value, mode)
    const { trackTask } = useBackgroundTasks()
    const titleMap = { new: '展开', replace: '重新展开', append: '继续展开' }
    trackTask({ id: task_id, task_type: 'outline_expand', title: `${titleMap[mode]}第${expandTarget.value.chapter_number}卷` })
    showExpand.value = false
    msg.success(`${titleMap[mode]}任务已提交，可在右下角查看进度`)
  } catch (e: any) { msg.error('展开失败：' + formatError(e)) }
  finally { expanding.value = false }
}
// 预览弹窗里点「重新展开（覆盖）」：先确认，再进入覆盖模式展开弹窗
async function reExpandFromPreview() {
  const o = previewData.value?.outline
  if (!o) return
  const oldCount = previewData.value?.chapter_count || 0
  if (!await msg.confirm(
    `确认删除当前 ${oldCount} 章并重新展开？\n旧章节内容将永久删除，新规划从原章号开始。`,
    '重新展开确认',
  )) return
  expandTarget.value = o
  expandCount.value = 3
  expandMode.value = 'replace'
  showPreview.value = false
  showExpand.value = true
}
// 预览弹窗里点「继续展开（追加）」：保留旧章节，在后面追加 N 章
function appendFromPreview() {
  const o = previewData.value?.outline
  if (!o) return
  expandTarget.value = o
  expandCount.value = 2
  expandMode.value = 'append'
  showPreview.value = false
  showExpand.value = true
}
function openBatchExpand() {
  batchCount.value = 3
  showBatchExpand.value = true
}
async function doBatchExpand() {
  batchExpanding.value = true
  try {
    const { task_id, pending_count } = await API.outline.batchExpand(batchCount.value)
    const { trackTask } = useBackgroundTasks()
    trackTask({ id: task_id, task_type: 'outline_expand', title: `批量展开 ${pending_count} 卷大纲` })
    showBatchExpand.value = false
    msg.success(`批量展开任务已提交（${pending_count} 卷），可在右下角查看进度`)
  } catch (e: any) { msg.error('批量展开失败：' + formatError(e)) }
  finally { batchExpanding.value = false }
}
async function viewExpansion(o: any) {
  try {
    const data = await API.outline.getChapters(o.id)
    previewData.value = { outline: o, ...data }
    // 默认选中第一个 tab
    activeTab.value = String(data.chapters?.[0]?.id || '')
    showPreview.value = true
  }
  catch (e: any) { msg.error('加载失败：' + formatError(e)) }
}
async function deleteExpansion() {
  if (!previewData.value) return
  if (!await msg.confirm(`确认删除此大纲展开的所有 ${previewData.value.chapter_count} 章？`)) return
  try { await API.outline.deleteChapters(previewData.value.outline.id); await refreshOutlines(); showPreview.value = false; msg.success('已删除') }
  catch (e: any) { msg.error('删除失败：' + formatError(e)) }
}
</script>

<template>
  <div class="outline-page">
    <div class="page-actions">
      <a-tag :color="isOneToMany ? 'green' : 'blue'" style="font-size:13px;padding:2px 12px;">{{ modeLabel }}</a-tag>
      <a-button v-if="isOneToMany && hasUnexpanded" @click="openBatchExpand" :loading="batchExpanding">
        批量展开
      </a-button>
      <a-button @click="onManualCreate">手动创建</a-button>
      <a-button type="primary" :loading="generating" @click="openContinue">
        {{ outlines && outlines.length ? '续写大纲' : 'AI 生成大纲' }}
      </a-button>
    </div>

    <!-- 待补充物品/地点 -->
    <a-alert
      v-if="pendingEntities && pendingEntities.total > 0"
      type="warning" show-icon closable style="margin-bottom:12px;cursor:pointer;"
      @close="pendingEntities = null"
      @click="showPendingModal = true"
    >
      <template #message>
        大纲中引用了 <b>{{ pendingEntities.pending_items?.length || 0 }}</b> 个新物品和 <b>{{ pendingEntities.pending_locations?.length || 0 }}</b> 个新地点尚未录入 — 点击查看详情
      </template>
      <template #action>
        <a-button size="small" type="primary" :loading="fillingEntities" @click.stop="fillPendingEntities">一键生成</a-button>
      </template>
    </a-alert>

    <!-- 待补充详情弹窗 -->
    <a-modal v-model:open="showPendingModal" title="待补充物品/地点" width="600px">
      <div v-if="pendingEntities">
        <h4 style="margin-bottom:8px;color:#D49A4E;">📦 新物品（{{ pendingEntities.pending_items?.length || 0 }}）</h4>
        <div v-if="pendingEntities.pending_items?.length" style="margin-bottom:16px;">
          <div v-for="(it, i) in pendingEntities.pending_items" :key="i" style="padding:6px 0;border-bottom:1px solid #f0f0f0;font-size:13px;">
            <b>{{ it.name }}</b>
            <a-tag size="small" style="margin-left:6px;">{{ it.category }}</a-tag>
            <span v-if="it.from_chapter" style="color:#999;font-size:11px;margin-left:6px;">来自第{{ it.from_chapter }}章</span>
            <div v-if="it.description" style="color:#666;font-size:12px;margin-top:2px;">{{ it.description }}</div>
          </div>
        </div>
        <a-empty v-else description="暂无" :image-style="{height:'30px'}" />

        <h4 style="margin-bottom:8px;color:#D49A4E;">📍 新地点（{{ pendingEntities.pending_locations?.length || 0 }}）</h4>
        <div v-if="pendingEntities.pending_locations?.length">
          <div v-for="(loc, i) in pendingEntities.pending_locations" :key="i" style="padding:6px 0;border-bottom:1px solid #f0f0f0;font-size:13px;">
            <b>{{ loc.name }}</b>
            <a-tag size="small" style="margin-left:6px;">{{ loc.location_type }}</a-tag>
            <span v-if="loc.from_chapter" style="color:#999;font-size:11px;margin-left:6px;">来自第{{ loc.from_chapter }}章</span>
            <div v-if="loc.description" style="color:#666;font-size:12px;margin-top:2px;">{{ loc.description }}</div>
          </div>
        </div>
        <a-empty v-else description="暂无" :image-style="{height:'30px'}" />
      </div>
      <template #footer>
        <a-button @click="showPendingModal = false">关闭</a-button>
        <a-button type="primary" :loading="fillingEntities" @click="fillPendingEntities">AI 生成全部</a-button>
      </template>
    </a-modal>

    <div v-if="outlines && outlines.length" class="outline-list">
      <OutlineCard
        v-for="o in outlines"
        :key="o.id"
        :outline="o"
        :mode="isOneToMany ? 'one_to_many' : 'one_to_one'"
        @expand="openExpand"
        @edit="openEdit"
        @delete="onDelete"
      />
    </div>
    <div v-if="outlineTotal > pageSize" class="outline-pagination">
      <a-pagination
        v-model:current="currentPage"
        v-model:page-size="pageSize"
        :total="outlineTotal"
        :page-size-options="['10', '20', '50']"
        show-size-changer
        show-total
        size="small"
      />
    </div>
    <a-empty v-else-if="!outlines || !outlines.length" description="暂无大纲，点击 AI 生成" />

    <!-- 手动创建弹窗 -->
    <a-modal v-model:open="showManualCreate" title="手动创建大纲" width="520px">
      <a-form layout="vertical">
        <a-row :gutter="12">
          <a-col :span="8">
            <a-form-item label="章节序号">
              <a-input-number v-model:value="manualForm.chapter_number" :min="1" style="width:100%" />
            </a-form-item>
          </a-col>
          <a-col :span="16">
            <a-form-item label="标题">
              <a-input v-model:value="manualForm.title" placeholder="章节标题" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="梗概">
          <a-textarea v-model:value="manualForm.summary" :rows="3" placeholder="200字以内的章节概要" />
        </a-form-item>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="情感基调">
              <a-input v-model:value="manualForm.emotion" placeholder="如：压抑→反击→暗爽" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="叙事目标">
              <a-input v-model:value="manualForm.goal" placeholder="本章在全书中的目的" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="情节要点（每行一个）">
          <a-textarea v-model:value="manualForm.key_points_text" :rows="3" placeholder="每行一个情节点" />
        </a-form-item>
      </a-form>
      <template #footer>
        <a-button @click="showManualCreate = false">取消</a-button>
        <a-button type="primary" @click="submitManualCreate">创建</a-button>
      </template>
    </a-modal>

    <!-- 生成弹窗 -->
    <a-modal v-model:open="showGen" title="AI 生成大纲" width="400px">
      <a-form layout="vertical">
        <a-form-item :label="isOneToMany ? '卷数' : '章数'"><a-input-number v-model:value="genCount" :min="3" :max="30" /></a-form-item>
      </a-form>
      <template #footer><a-button @click="showGen = false">取消</a-button><a-button type="primary" :loading="generating" @click="onGenerate">生成</a-button></template>
    </a-modal>

    <!-- 续写弹窗 -->
    <a-modal v-model:open="showContinue" title="续写大纲" width="560px">
      <a-form layout="vertical">
        <a-form-item label="续写章节数">
          <a-radio-group v-model:value="continueForm.chapter_count" button-style="solid">
            <a-radio-button v-for="n in chapterCountOptions" :key="n" :value="n">{{ n }} 章</a-radio-button>
          </a-radio-group>
        </a-form-item>
        <a-form-item label="故事发展方向">
          <a-textarea v-model:value="continueForm.story_direction" :rows="3" placeholder="描述故事接下来的发展方向，例如：主角进入秘境修炼，遇到新的挑战..." />
        </a-form-item>
        <a-form-item label="情节阶段">
          <a-select v-model:value="continueForm.plot_stage" placeholder="选择当前情节阶段" allow-clear>
            <a-select-option value="开端">开端</a-select-option>
            <a-select-option value="发展">发展</a-select-option>
            <a-select-option value="高潮">高潮</a-select-option>
            <a-select-option value="转折">转折</a-select-option>
            <a-select-option value="结局">结局</a-select-option>
          </a-select>
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item :label="`叙事视角`">
              <a-select v-model:value="continueForm.narrative_pov" :placeholder="`按小说设定（${projectDefaultPov}）`" allow-clear>
                <a-select-option value="">{{ `按小说设定（${projectDefaultPov}）` }}</a-select-option>
                <a-select-option value="第三人称">第三人称（他/她）</a-select-option>
                <a-select-option value="第一人称">第一人称（我）</a-select-option>
                <a-select-option value="全知视角">全知视角</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="AI 模型">
              <a-select
                v-model:value="continueForm.ai_model"
                :placeholder="defaultModelName ? `使用默认（${defaultModelName}）` : '使用默认模型'"
                allow-clear
                show-search
                option-filter-prop="label"
                :loading="loadingModels"
              >
                <a-select-option value="">{{ defaultModelName ? `使用默认（${defaultModelName}）` : '使用默认模型' }}</a-select-option>
                <a-select-option v-for="m in remoteModels" :key="m.id" :value="m.id" :label="m.id">{{ m.id }}</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="其他要求">
          <a-textarea v-model:value="continueForm.other_requirements" :rows="2" placeholder="其他特殊要求，例如：需要包含战斗场景、增加感情线..." />
        </a-form-item>
      </a-form>
      <template #footer>
        <a-button @click="showContinue = false">取消</a-button>
        <a-button type="primary" :loading="generating" @click="onContinue">开始续写</a-button>
      </template>
    </a-modal>

    <!-- 编辑弹窗（含关键点/角色/组织编辑，不丢数据）-->
    <a-modal :open="!!editing" @update:open="(v:any) => { if(!v) editing = null }" title="编辑大纲" width="620px" v-if="editing">
      <a-form layout="vertical">
        <a-form-item label="标题"><a-input v-model:value="editForm.title" /></a-form-item>
        <a-form-item label="梗概"><a-textarea v-model:value="editForm.summary" :rows="4" /></a-form-item>
        <a-form-item label="情节要点（每行一个）"><a-textarea v-model:value="editForm.key_points_text" :rows="3" placeholder="每行一个关键情节点" /></a-form-item>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="涉及角色">
              <a-select
                v-model:value="editForm.characters"
                mode="tags"
                placeholder="选择或输入角色名，回车添加"
                :options="characterOptions.map(c => ({ value: c.name, label: c.label }))"
                option-filter-prop="label"
                :token-separators="[',', '，', '、']"
                style="width:100%"
              />
              <div class="field-hint">可从已有角色选择，也可直接输入新名字</div>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="涉及组织">
              <a-select
                v-model:value="editForm.organizations"
                mode="tags"
                placeholder="选择或输入组织名，回车添加"
                :options="organizationOptions.map(o => ({ value: o.name, label: o.label }))"
                option-filter-prop="label"
                :token-separators="[',', '，', '、']"
                style="width:100%"
              />
              <div class="field-hint">可从已有组织选择，也可直接输入新名字</div>
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="12">
          <a-col :span="12"><a-form-item label="情感基调"><a-input v-model:value="editForm.emotion" /></a-form-item></a-col>
          <a-col :span="12"><a-form-item label="叙事目标"><a-input v-model:value="editForm.goal" /></a-form-item></a-col>
        </a-row>

        <!-- AI 额外字段（爽点/钩子/伏笔等）-->
        <a-form-item>
          <template #label>
            <span>✨ AI 额外字段</span>
            <span style="font-size:11px;color:#999;font-weight:normal;margin-left:6px;">AI 生成大纲时可能添加（如爽点设计、读者钩子、伏笔埋设等），可查看和编辑</span>
          </template>
          <div v-if="editForm.extraFields.length" class="extra-edit-list">
            <div v-for="(f, i) in editForm.extraFields" :key="i" class="extra-edit-item">
              <div class="extra-edit-head">
                <span class="extra-edit-label">{{ fieldLabel(f.key) }}</span>
                <span class="extra-edit-key">{{ f.key }}</span>
                <a-button type="link" danger size="small" @click="removeExtraField(i)">删除</a-button>
              </div>
              <a-textarea v-model:value="f.value" :rows="2" />
            </div>
          </div>
          <div v-else class="extra-empty">暂无额外字段</div>
          <div class="extra-add">
            <a-input v-model:value="newFieldKey" placeholder="字段名（如 shuang_design）" style="width:200px" @press-enter="addExtraField" />
            <a-button size="small" @click="addExtraField">添加自定义字段</a-button>
          </div>
        </a-form-item>
      </a-form>
      <template #footer><a-button @click="editing = null">取消</a-button><a-button type="primary" @click="onSave">保存</a-button></template>
    </a-modal>

    <!-- 展开弹窗 -->
    <a-modal v-model:open="showExpand" :title="expandMode === 'replace' ? '重新展开（覆盖）' : expandMode === 'append' ? '继续展开（追加）' : '展开为多章'" width="440px">
      <a-alert v-if="expandMode === 'replace'" type="warning" show-icon style="margin-bottom:12px;" message="将删除该卷当前所有章节，重新生成规划" />
      <a-alert v-else-if="expandMode === 'append'" type="info" show-icon style="margin-bottom:12px;" message="保留已有章节，在其后追加新章节（sub_index 续接）" />
      <p>将第{{ expandTarget?.chapter_number }}卷「{{ expandTarget?.title }}」{{ expandMode === 'replace' ? '覆盖重展为' : expandMode === 'append' ? '继续追加' : '展开为' }} {{ expandCount }} 章：</p>
      <a-input-number v-model:value="expandCount" :min="2" :max="10" addon-before="章节数" style="width:100%;margin-bottom:12px" />
      <div style="display:flex;align-items:center;gap:8px">
        <span style="font-size:12px;color:#8C8C8C">展开策略：</span>
        <a-radio-group v-model:value="expandStrategy" size="small">
          <a-radio-button value="balanced">均衡</a-radio-button>
          <a-radio-button value="climax">高潮重点</a-radio-button>
          <a-radio-button value="detail">细节丰富</a-radio-button>
        </a-radio-group>
      </div>
      <template #footer>
        <a-button @click="showExpand = false">取消</a-button>
        <a-button type="primary" :danger="expandMode === 'replace'" :loading="expanding" @click="doExpand">
          {{ expanding ? '规划中…' : (expandMode === 'replace' ? '确认覆盖重展' : expandMode === 'append' ? '继续追加' : '展开') }}
        </a-button>
      </template>
    </a-modal>

    <!-- 批量展开弹窗 -->
    <a-modal v-model:open="showBatchExpand" title="批量展开所有大纲" width="440px">
      <p>将所有未展开的大纲卷一次性展开为多章（后台按顺序执行）：</p>
      <a-input-number v-model:value="batchCount" :min="2" :max="10" addon-before="每卷章节数" style="width:100%" />
      <p style="font-size:12px;color:#8C8C8C;margin-top:8px;">建议每卷 2-5 章。任务可在右下角浮窗查看进度。</p>
      <template #footer>
        <a-button @click="showBatchExpand = false">取消</a-button>
        <a-button type="primary" :loading="batchExpanding" @click="doBatchExpand">{{ batchExpanding ? '提交中…' : '开始批量展开' }}</a-button>
      </template>
    </a-modal>

    <!-- 已展开预览（Tab 浏览器模式 + 彩色标签） -->
    <a-modal v-model:open="showPreview" :title="`展开预览 — 第${previewData?.outline?.chapter_number}卷`" width="780px" :footer="null">
      <div v-if="previewData">
        <div style="margin-bottom:12px;">
          <a-tag color="success">已展开 {{ previewData.chapter_count }} 章</a-tag>
          <a-button size="small" style="margin-left:8px" @click="appendFromPreview">➕ 继续展开</a-button>
          <a-button size="small" style="margin-left:8px" @click="reExpandFromPreview">🔄 重新展开</a-button>
          <a-button danger size="small" style="margin-left:8px" @click="deleteExpansion">删除展开</a-button>
        </div>
        <a-tabs v-model:active-key="activeTab" type="card" size="small">
          <a-tab-pane
            v-for="ch in (previewData.chapters || [])"
            :key="String(ch.id)"
            :tab="'第' + ch.sub_index + '节 ' + ch.title + (ch.expansion_plan?.rhythm_tag ? ' 「' + ch.expansion_plan.rhythm_tag + '」' : '')"
          >
            <div v-if="ch.expansion_plan" style="padding:8px 0">
              <LazyExpansionPlanView
                :no-modal="true"
                :open="true"
                :plan="ch.expansion_plan"
                :chapter-number="ch.chapter_number || 0"
                :chapter-title="ch.title"
              />
            </div>
            <div v-else class="plan-empty">暂无规划数据</div>
          </a-tab-pane>
        </a-tabs>
      </div>
    </a-modal>

    <!-- 新角色检测弹窗 -->
    <a-modal v-model:open="showNewChars" title="检测到新角色" width="420px">
      <p>大纲中出现了以下新角色，是否立即生成角色档案？</p>
      <div style="margin: 12px 0;">
        <a-tag v-for="name in newCharNames" :key="name" color="purple" style="margin: 2px 4px;">{{ name }}</a-tag>
      </div>
      <p style="font-size:12px;color:#8C8C8C;">生成后可在角色页面查看和编辑详细信息。</p>
      <template #footer>
        <a-button @click="showNewChars = false">跳过</a-button>
        <a-button type="primary" :loading="generatingChars" @click="onGenerateNewChars">
          {{ generatingChars ? '生成中…' : '立即生成' }}
        </a-button>
      </template>
    </a-modal>
  </div>
</template>

<style scoped>
.outline-page { display: flex; flex-direction: column; gap: 16px; }
.outline-pagination { display: flex; justify-content: center; padding: 12px 0 4px; }
.page-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.outline-list { display: flex; flex-direction: column; gap: 10px; }
.outline-item { background: #fff; border: 1px solid #E8E4DC; border-radius: 8px; overflow: hidden; transition: border-color .2s, box-shadow .2s; }
.outline-item:hover { border-color: #B8CDD1; box-shadow: 0 2px 12px rgba(43,43,43,0.08); }
.item-head { display: flex; align-items: center; gap: 8px; padding: 12px 16px; border-bottom: 1px solid #F5F2EB; }
.item-no { font-size: 12px; color: #4D8088; font-weight: 600; background: #EAF0F1; padding: 2px 8px; border-radius: 4px; flex-shrink: 0; }
.item-title { font-size: 15px; font-weight: 600; color: #2B2B2B; flex: 1; }
.item-actions { display: flex; flex-shrink: 0; }
.item-body { padding: 12px 16px; }
.item-footer { display: flex; align-items: center; justify-content: space-between; padding: 8px 16px; border-top: 1px solid #F5F2EB; background: #FBFAF7; }
.footer-left { display: flex; gap: 4px; }
.content-section { margin-bottom: 12px; }
.content-section:last-child { margin-bottom: 0; }
.section-label { font-size: 12px; font-weight: 600; color: #8C8C8C; margin-bottom: 6px; }
.section-text { font-size: 14px; color: #595959; line-height: 1.7; }
.content-section.chars { background: #F9F0FC; border-radius: 6px; padding: 10px 12px; }
.content-section.orgs { background: #F0F5FA; border-radius: 6px; padding: 10px 12px; }
.content-section.goal-sec { background: #F0F5F5; border-radius: 6px; padding: 10px 12px; }
.content-section.extra-sec { background: #FFFBE6; border-radius: 6px; padding: 10px 12px; border: 1px dashed #FFE58F; }
.extra-list { display: flex; flex-direction: column; gap: 8px; }
.extra-item { display: flex; flex-direction: column; gap: 2px; }
.extra-key { font-size: 12px; font-weight: 600; color: #AD6800; }
.extra-val { font-size: 13px; color: #595959; line-height: 1.7; white-space: pre-wrap; word-break: break-word; }
.extra-edit-list { display: flex; flex-direction: column; gap: 10px; margin-bottom: 10px; }
.extra-edit-item { background: #FAFAF7; border: 1px solid #F0F0F0; border-radius: 6px; padding: 8px 10px; }
.extra-edit-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.extra-edit-label { font-size: 13px; font-weight: 600; color: #2B2B2B; }
.extra-edit-key { font-size: 11px; color: #BFBFBF; font-family: monospace; }
.extra-edit-head :deep(.ant-btn) { margin-left: auto; padding: 0 4px; height: auto; }
.extra-empty { font-size: 12px; color: #BFBFBF; padding: 8px 0; }
.extra-add { display: flex; gap: 8px; align-items: center; }
.char-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.key-points { display: flex; flex-direction: column; gap: 6px; }
.emotion-tag { margin-bottom: 8px; }
.field-hint { font-size: 11px; color: #999; margin-top: 4px; }
.kp-item { display: flex; gap: 8px; font-size: 13px; color: #595959; align-items: flex-start; }
.kp-dot { width: 18px; height: 18px; border-radius: 50%; background: #4D8088; color: #fff; font-size: 11px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.scene-list { display: flex; flex-direction: column; gap: 6px; }
.scene-item { background: #FAFAF7; border-radius: 6px; padding: 8px 10px; }
.scene-title { font-weight: 600; font-size: 13px; color: #2B2B2B; }
.scene-desc { font-size: 13px; color: #8C8C8C; display: block; margin-top: 2px; }
.preview-chap { background: #FAFAF7; border-radius: 6px; padding: 10px 12px; margin-bottom: 8px; }
.preview-chap-head { display: flex; gap: 8px; margin-bottom: 4px; }
.preview-chap-no { font-size: 12px; color: #4D8088; font-weight: 600; }
.preview-chap-title { font-size: 14px; }
.plan-empty { font-size: 12px; color: #BFBFBF; padding: 8px 0; }
.tag-row { display: flex; flex-wrap: wrap; gap: 6px; }
</style>
