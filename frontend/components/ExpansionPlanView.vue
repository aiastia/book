<script setup lang="ts">
// 章节规划只读详情 — 自动渲染 expansion_plan 全部字段，未来 AI 加新字段无需改这里
const props = defineProps<{
  open: boolean
  chapterNumber: number
  chapterTitle?: string
  plan?: Record<string, any> | null
  chapterSummary?: string
}>()

const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

// ===== 中文标签映射（与 outline.vue FIELD_LABELS 一致）=====
const FIELD_LABELS: Record<string, string> = {
  plot_summary: '剧情摘要',
  summary: '剧情摘要',
  key_events: '关键事件',
  character_focus: '涉及角色',
  emotional_tone: '情感基调',
  emotional_arc: '情绪弧线',
  conflict_type: '冲突类型',
  narrative_goal: '叙事目标',
  estimated_words: '预估字数',
  scenes: '场景设定',
  hook: '结尾钩子',
  hook_type: '钩子类型',
  shuang_design: '爽点设计',
  reader_hook: '读者追读理由',
  rhythm_tag: '节奏标记',
  scene_anchor: '场景锚点',
  character_intents: '角色微意图',
  ending_type: '结尾类型',
  chapter_breath: '章节节奏',
  obstacle_type: '障碍类型',
  foreshadow_plant: '伏笔埋设',
  foreshadow_advance: '伏笔推进',
  notes: '备注',
}

// ===== 工具函数 =====
const knownFieldKeys = new Set(['plot_summary', 'summary', 'key_events', 'character_focus'])
const planData = computed(() => props.plan || {})

// 剧情摘要（优先 plot_summary）
const summary = computed(() =>
  planData.value.plot_summary || planData.value.summary || props.chapterSummary || ''
)

// 关键事件（数组→字符串列表）
const keyEvents = computed<string[]>(() => {
  const v = planData.value.key_events
  return Array.isArray(v) ? v.map((e: any) => (typeof e === 'object' ? JSON.stringify(e) : String(e))) : []
})

// 涉及角色
const characterFocus = computed<string[]>(() =>
  Array.isArray(planData.value.character_focus) ? planData.value.character_focus : []
)

// 基础信息表格（情感基调/冲突/字数/节奏标签）
const basicInfo = computed(() => {
  const rows: Array<{ label: string; value: string }> = []
  const tone = planData.value.emotional_tone || ''
  const conflict = planData.value.conflict_type || ''
  const words = planData.value.estimated_words
  const rhythm = planData.value.rhythm_tag || ''
  if (tone) rows.push({ label: '情感基调', value: tone })
  if (conflict) rows.push({ label: '冲突类型', value: conflict })
  if (rhythm) rows.push({ label: '节奏标签', value: rhythm })
  if (words) rows.push({ label: '预估字数', value: words + ' 字' })
  return rows
})

// 富字段：除标准字段外的所有额外字段（自动遍历，未来 AI 加新字段自动显示）
type FieldEntry = { key: string; label: string; value: string; isArray: boolean }
const extraFields = computed<FieldEntry[]>(() => {
  const entries: FieldEntry[] = []
  const skipKeys = new Set([
    'plot_summary', 'summary', 'key_events', 'character_focus',
    'emotional_tone', 'conflict_type', 'estimated_words', 'rhythm_tag',
    'title', 'sub_index', 'outline_id',
  ])
  for (const [k, v] of Object.entries(planData.value)) {
    if (skipKeys.has(k)) continue
    if (v == null || v === '') continue
    const label = FIELD_LABELS[k] || k
    if (Array.isArray(v)) {
      const text = v.map((x: any) => (typeof x === 'object' ? JSON.stringify(x) : String(x))).join('；')
      if (text) entries.push({ key: k, label, value: text, isArray: true })
    } else if (typeof v === 'object') {
      const text = JSON.stringify(v, null, 2)
      entries.push({ key: k, label, value: text, isArray: false })
    } else {
      entries.push({ key: k, label, value: String(v), isArray: false })
    }
  }
  return entries
})

function close() {
  emit('update:open', false)
}
</script>

<template>
  <a-modal
    :open="open"
    :title="`📋 章节规划 · 第${chapterNumber}章`"
    :width="700"
    centered
    :footer="null"
    @cancel="close"
  >
    <div v-if="chapterTitle" class="view-subtitle">章节：{{ chapterTitle }}</div>

    <!-- 基础信息表格 -->
    <a-descriptions v-if="basicInfo.length" :column="2" size="small" bordered class="view-desc">
      <a-descriptions-item v-for="row in basicInfo" :key="row.label" :label="row.label" :span="1">
        {{ row.value }}
      </a-descriptions-item>
    </a-descriptions>

    <!-- 剧情摘要 -->
    <div v-if="summary" class="view-block">
      <div class="view-block-title">📝 剧情摘要</div>
      <div class="view-block-text">{{ summary }}</div>
    </div>

    <!-- 关键事件 -->
    <div v-if="keyEvents.length" class="view-block">
      <div class="view-block-title">⚡ 关键事件</div>
      <div class="tag-row">
        <a-tag v-for="(ev, i) in keyEvents" :key="i" color="blue">{{ ev }}</a-tag>
      </div>
    </div>

    <!-- 涉及角色 -->
    <div v-if="characterFocus.length" class="view-block">
      <div class="view-block-title">👥 涉及角色</div>
      <div class="tag-row">
        <a-tag v-for="(c, i) in characterFocus" :key="i" color="orange">{{ c }}</a-tag>
      </div>
    </div>

    <!-- 叙事目标 -->
    <div v-if="planData.narrative_goal" class="view-block">
      <div class="view-block-title">🎯 叙事目标</div>
      <div class="view-block-text">{{ planData.narrative_goal }}</div>
    </div>

    <!-- 富字段：自动遍历所有额外字段（爽点/钩子/情绪弧/场景锚点/微意图等） -->
    <div v-if="extraFields.length" class="view-block extra-block">
      <div class="view-block-title">📌 更多设定（{{ extraFields.length }}）</div>
      <div class="extra-grid">
        <div v-for="f in extraFields" :key="f.key" class="extra-item">
          <span class="extra-label">{{ f.label }}</span>
          <span class="extra-value" :style="{ whiteSpace: f.isArray ? 'normal' : 'pre-wrap' }">{{ f.value }}</span>
        </div>
      </div>
    </div>

    <a-empty v-if="!summary && !keyEvents.length && !characterFocus.length && !extraFields.length && !planData.narrative_goal"
      description="该章节暂无规划" style="margin: 40px 0" />
  </a-modal>
</template>

<style scoped>
.view-subtitle { font-size: 13px; color: #8C8C8C; margin-bottom: 14px; }
.view-desc { margin-bottom: 16px; }
.view-block { margin-bottom: 16px; }
.view-block-title { font-size: 13px; font-weight: 600; color: #4D8088; margin-bottom: 8px; }
.view-block-text { font-size: 14px; color: #595959; line-height: 1.7; white-space: pre-wrap; }
.tag-row { display: flex; flex-wrap: wrap; gap: 6px; }
.extra-block { background: #FFFBE6; border-radius: 8px; padding: 12px 14px; border: 1px dashed #FFE58F; }
.extra-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.extra-item { display: flex; flex-direction: column; gap: 2px; }
.extra-label { font-size: 12px; font-weight: 600; color: #AD6800; }
.extra-value { font-size: 13px; color: #595959; line-height: 1.7; word-break: break-word; }
</style>
