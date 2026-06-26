<script setup lang="ts">
// 章节规划编辑器 — 编辑基础字段，保存时合并回原 plan 保留 AI 生成的富字段
import { apiGet } from '~/composables/useApi'
import { useProject } from '~/composables/useProject'
import { useProjectApi } from '~/composables/useProjectApi'

const props = defineProps<{
  open: boolean
  chapterId: number
  chapterNumber: number
  chapterTitle?: string
  planData?: Record<string, any> | null
  chapterSummary?: string
  outlineId?: number | null  // 所属大纲 ID，用于触发 AI 重新规划
}>()

const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'saved', plan: Record<string, any>): void
}>()

const { currentProjectId } = useProject()
const api = useProjectApi()
const msg = useMessage()

// 表单字段
const summary = ref('')
const emotionalTone = ref('')
const conflictType = ref('')
const narrativeGoal = ref('')

// 关键事件
const keyEvents = ref<string[]>([])
const keyEventInput = ref('')

// 涉及角色
const availableCharacters = ref<any[]>([])
const characterFocus = ref<string[]>([])
const loadingCharacters = ref(false)

const saving = ref(false)
const regenerating = ref(false)

// AI 重新规划：对该卷重新展开（覆盖模式），AI 重新生成该卷所有子章节的规划
const canRegenerate = computed(() => props.outlineId != null && props.outlineId > 0)

async function onRegenerate() {
  if (!props.outlineId) return
  // 先查该卷现有章节数，复用此数量
  let existingCount = 3
  try {
    const chs = await apiGet<any>(`/api/projects/${currentProjectId.value}/outlines/${props.outlineId}/chapters`)
    if (chs?.chapter_count) existingCount = chs.chapter_count
  } catch { /* 取不到就用默认3 */ }

  if (!await msg.confirm(
    `AI 将重新展开该卷的全部 ${existingCount} 节子章节。\n旧规划数据将被覆盖，新规划从原章号开始。`,
    '重新展开整卷',
  )) return
  regenerating.value = true
  try {
    const { task_id } = await api.expandOutlineAsync(props.outlineId, {
      target_chapter_count: existingCount,
      mode: 'replace',
    })
    const { trackTask } = useBackgroundTasks()
    trackTask({ id: task_id, task_type: 'outline_expand', title: `重新展开第${props.chapterNumber}章所属卷(${existingCount}节)` })
    msg.success('重新规划任务已提交，完成后刷新查看')
    emit('saved', {})
    close()
  } catch (e: any) {
    msg.error('重新规划失败：' + formatError(e))
  } finally {
    regenerating.value = false
  }
}

// 冲突类型/情感基调候选项
const conflictTypeOptions = ['人物冲突', '环境冲突', '内心冲突', '理念冲突', '势力冲突', '命运冲突']
const emotionalToneOptions = ['紧张激烈', '温馨治愈', '悲壮压抑', '轻松幽默', '悬疑烧脑', '热血激昂', '哀婉凄美']

// ===== 富字段参考（只读，保存时自动保留）=====
const FIELD_LABELS: Record<string, string> = {
  plot_summary: '剧情摘要', summary: '剧情摘要',
  key_events: '关键事件', character_focus: '涉及角色',
  emotional_tone: '情感基调', conflict_type: '冲突类型',
  narrative_goal: '叙事目标', estimated_words: '预估字数',
  emotional_arc: '情绪弧线', hook: '结尾钩子',
  hook_type: '钩子类型', shuang_design: '爽点设计',
  reader_hook: '读者追读理由', rhythm_tag: '节奏标记',
  scene_anchor: '场景锚点', character_intents: '角色微意图',
  ending_type: '结尾类型', chapter_breath: '章节节奏',
  obstacle_type: '障碍类型', scenes: '场景设定',
  info_asymmetry: '信息差', shock_level: '震惊层级',
  spectator_layers: '围观分层', emotional_rhythm: '情绪节奏',
  protagonist_style: '主角逼格',
}

const EDIT_KEYS = new Set([
  'plot_summary', 'summary', 'key_events', 'character_focus',
  'emotional_tone', 'emotional_arc', 'conflict_type', 'narrative_goal',
  'estimated_words', 'sub_index', 'title', 'outline_id',
])

type FieldEntry = { key: string; label: string; value: string; readOnly?: boolean }
const extraFields = computed<FieldEntry[]>(() => {
  const plan = props.planData
  if (!plan || typeof plan !== 'object') return []
  const entries: FieldEntry[] = []
  for (const [k, v] of Object.entries(plan)) {
    if (EDIT_KEYS.has(k)) continue
    if (v == null || v === '' || (Array.isArray(v) && v.length === 0) || (typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === 0)) continue

    // shuang_design：拆成子字段（可编辑）
    if (k === 'shuang_design' && typeof v === 'object' && v) {
      const subFields: [string, string][] = [
        ['info_asymmetry', '信息差'], ['shock_level', '震惊层级'],
        ['spectator_layers', '围观分层'], ['emotional_rhythm', '情绪节奏'],
        ['protagonist_style', '主角逼格'],
      ]
      for (const [sk, sl] of subFields) {
        const sv = (v as any)[sk]
        if (sv == null || sv === '') continue
        entries.push({ key: `shuang_design.${sk}`, label: sl, value: Array.isArray(sv) ? sv.join(' → ') : String(sv) })
      }
      continue
    }

    // character_intents：拆成每个角色（可编辑）
    if (k === 'character_intents' && Array.isArray(v)) {
      for (let i = 0; i < v.length; i++) {
        const item = v[i]
        if (typeof item !== 'object' || !item) continue
        const name = item.character || item.name || '?'
        let text = ''
        if (item.this_chapter_goal) text += `目标：${item.this_chapter_goal}`
        if (item.immediate_want) text += text ? `；当前欲求：${item.immediate_want}` : `当前欲求：${item.immediate_want}`
        if (text) entries.push({ key: `character_intents.${i}`, label: `角色「${name}」`, value: text })
      }
      continue
    }

    const label = FIELD_LABELS[k] || k
    const text = Array.isArray(v)
      ? v.map((x: any) => (typeof x === 'object' ? JSON.stringify(x) : String(x))).join('；')
      : typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v)
    if (text) entries.push({ key: k, label, value: text })
  }
  return entries
})

// 加载项目角色
async function loadCharacters() {
  loadingCharacters.value = true
  try {
    const list = await apiGet<any[]>(`/api/projects/${currentProjectId.value}/characters`)
    availableCharacters.value = (list || []).map((c: any) => ({
      name: c.name, role: c.role || '',
      label: c.role ? `${c.name}（${c.role}）` : c.name,
    }))
  } catch (e: any) {
    console.warn('加载角色失败', e)
  } finally {
    loadingCharacters.value = false
  }
}

// 当弹窗打开 / planData 变化时回填
watch(
  () => [props.open, props.planData, props.chapterSummary],
  ([isOpen]) => {
    if (!isOpen) return
    const plan = props.planData || {}
    // 摘要：优先 plot_summary（AI 格式），回退 summary（兼容旧数据）
    summary.value = plan.plot_summary || plan.summary || props.chapterSummary || ''
    keyEvents.value = Array.isArray(plan.key_events) ? [...plan.key_events] : []
    characterFocus.value = Array.isArray(plan.character_focus) ? [...plan.character_focus] : []
    emotionalTone.value = plan.emotional_tone || ''
    conflictType.value = plan.conflict_type || ''
    narrativeGoal.value = plan.narrative_goal || ''
    keyEventInput.value = ''
  },
  { immediate: true }
)

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen && currentProjectId.value) loadCharacters()
  }
)

function addKeyEvent() {
  const v = keyEventInput.value.trim()
  if (v && !keyEvents.value.includes(v)) {
    keyEvents.value.push(v)
    keyEventInput.value = ''
  }
}
function removeKeyEvent(idx: number) {
  keyEvents.value.splice(idx, 1)
}

function close() {
  emit('update:open', false)
}

async function onSave() {
  if (keyEvents.value.length === 0) {
    msg.warning('请至少添加一个关键事件')
    return
  }
  if (characterFocus.value.length === 0) {
    msg.warning('请至少选择一个涉及角色')
    return
  }
  saving.value = true
  try {
    // 从 extraFields 编辑值重建结构化对象
    const extraMap: Record<string, any> = {}
    const sdSubs: Record<string, string> = {}
    const ciItems: Record<number, { character: string; text: string }> = {}
    for (const f of extraFields.value) {
      if (f.key.startsWith('shuang_design.')) {
        sdSubs[f.key.split('.')[1]] = f.value
      } else if (f.key.startsWith('character_intents.')) {
        const idx = parseInt(f.key.split('.')[1])
        if (!isNaN(idx)) ciItems[idx] = { character: f.label.replace('角色「', '').replace('」', ''), text: f.value }
      } else {
        extraMap[f.key] = f.value
      }
    }
    // 重建 shuang_design 对象
    let rebuiltShuang: any = null
    if (Object.keys(sdSubs).length > 0) {
      rebuiltShuang = { ...sdSubs }
      // spectator_layers 用 → 分隔的还原为数组
      if (rebuiltShuang.spectator_layers && rebuiltShuang.spectator_layers.includes(' → ')) {
        rebuiltShuang.spectator_layers = rebuiltShuang.spectator_layers.split(' → ').map((s: string) => s.trim())
      }
    }
    // 重建 character_intents 数组
    let rebuiltCI: any[] | null = null
    const ciKeys = Object.keys(ciItems).sort((a, b) => Number(a) - Number(b))
    if (ciKeys.length > 0) {
      rebuiltCI = ciKeys.map(k => {
        const { character, text } = ciItems[Number(k)]
        const goalMatch = text.match(/目标：(.+?)(?:；当前欲求|$)/)
        const wantMatch = text.match(/当前欲求：(.+)$/)
        return {
          character,
          this_chapter_goal: goalMatch ? goalMatch[1].trim() : '',
          immediate_want: wantMatch ? wantMatch[1].trim() : '',
        }
      })
    }

    const originalPlan = props.planData && typeof props.planData === 'object' ? { ...props.planData } : {}
    const merged: Record<string, any> = {
      ...originalPlan,
      plot_summary: summary.value,
      key_events: keyEvents.value,
      character_focus: characterFocus.value,
      emotional_tone: emotionalTone.value,
      conflict_type: conflictType.value,
      narrative_goal: narrativeGoal.value,
    }
    // 覆盖编辑过的额外字段
    for (const [k, v] of Object.entries(extraMap)) {
      merged[k] = v
    }
    if (rebuiltShuang) merged.shuang_design = rebuiltShuang
    if (rebuiltCI) merged.character_intents = rebuiltCI

    await api.updateChapter(props.chapterId, { expansion_plan: merged })
    msg.success('规划保存成功')
    emit('saved', merged)
    close()
  } catch (e: any) {
    msg.error('保存失败：' + formatError(e))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <a-modal
    :open="open"
    :title="`📋 编辑章节规划 · 第${chapterNumber}章`"
    :width="700"
    centered
    :destroy-on-close="true"
    @cancel="close"
  >
    <div v-if="chapterTitle" class="plan-subtitle">章节：{{ chapterTitle }}</div>

    <a-form layout="vertical" class="plan-form">
      <!-- 情节概要 -->
      <a-form-item label="情节概要" tooltip="简要描述本章的主要情节和故事走向">
        <a-textarea v-model:value="summary" :rows="4" placeholder="例如：主角得知身世真相，与反派在悬崖展开最终对决……" />
      </a-form-item>

      <!-- 关键事件 -->
      <a-form-item label="关键事件">
        <div class="tag-row">
          <a-tag v-for="(ev, i) in keyEvents" :key="i" closable color="blue" @close="removeKeyEvent(i)">{{ ev }}</a-tag>
        </div>
        <a-input-search
          v-model:value="keyEventInput"
          placeholder="输入关键事件后回车/点添加"
          enter-button="添加"
          size="small"
          @search="addKeyEvent"
        />
      </a-form-item>

      <!-- 涉及角色 -->
      <a-form-item label="涉及角色">
        <a-select
          v-model:value="characterFocus"
          mode="multiple"
          :loading="loadingCharacters"
          placeholder="选择本章主要角色"
          :options="availableCharacters.map(c => ({ value: c.name, label: c.label }))"
          :field-names="{ value: 'value', label: 'label' }"
          option-filter-prop="label"
        />
      </a-form-item>

      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="情感基调">
            <a-select v-model:value="emotionalTone" :options="emotionalToneOptions.map(o => ({ value: o, label: o }))" allow-clear placeholder="选择或清空" />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="冲突类型">
            <a-select v-model:value="conflictType" :options="conflictTypeOptions.map(o => ({ value: o, label: o }))" allow-clear placeholder="选择或清空" />
          </a-form-item>
        </a-col>
      </a-row>

      <!-- 叙事目标 -->
      <a-form-item label="叙事目标" tooltip="本章在整本书结构中要达成的目的">
        <a-textarea v-model:value="narrativeGoal" :rows="2" placeholder="例如：引出最终 BOSS、回收身世伏笔、完成主角成长弧线" />
      </a-form-item>

      <!-- AI 生成的其他富字段（只读参考，保存时不丢失） -->
      <div v-if="extraFields.length" class="extra-ref">
        <div class="extra-ref-title">📌 AI 生成的其他设定（可编辑，保存时保留）</div>
        <div class="extra-grid">
          <div v-for="f in extraFields" :key="f.key" class="extra-item">
            <span class="extra-label">{{ f.label }}</span>
            <a-textarea v-model:value="f.value" :rows="String(f.value).length > 80 ? 3 : 2" size="small" style="font-size:12px" />
          </div>
        </div>
      </div>
    </a-form>
    <template #footer>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <a-button v-if="canRegenerate" :loading="regenerating" @click="onRegenerate">🤖 重新展开整卷</a-button>
        <span v-else></span>
        <div>
          <a-button @click="close" :disabled="saving || regenerating">取消</a-button>
          <a-button type="primary" :loading="saving" @click="onSave" style="margin-left:8px">{{ saving ? '保存中…' : '保存' }}</a-button>
        </div>
      </div>
    </template>
  </a-modal>
</template>

<style scoped>
.plan-subtitle { font-size: 13px; color: #8C8C8C; margin-bottom: 12px; }
.plan-form { max-height: 60vh; overflow-y: auto; padding-right: 4px; }
.tag-row { margin-bottom: 8px; min-height: 24px; }
.tag-row :deep(.ant-tag) { margin-bottom: 4px; }
.word-hint { margin-left: 8px; color: #8C8C8C; font-size: 13px; }
.extra-ref { background: #FFFBE6; border: 1px dashed #FFE58F; border-radius: 8px; padding: 12px 14px; margin-top: 8px; }
.extra-ref-title { font-size: 12px; font-weight: 600; color: #AD6800; margin-bottom: 10px; }
.extra-grid { display: flex; flex-direction: column; gap: 10px; }
.extra-item { display: flex; flex-direction: column; gap: 2px; }
.extra-label { font-size: 12px; font-weight: 600; color: #AD6800; }
.extra-value { font-size: 13px; color: #595959; line-height: 1.7; word-break: break-word; white-space: pre-wrap; }
</style>
