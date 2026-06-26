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
  new_characters_needed: '需新增角色',
  notes: '备注',
}

// ===== 工具函数 =====
const SKIP_KEYS = new Set([
  'plot_summary', 'summary', 'key_events', 'character_focus',
  'emotional_tone', 'emotional_arc', 'conflict_type', 'rhythm_tag',
  'narrative_goal', 'estimated_words', 'hook', 'scene_anchor', 'reader_hook',
  'title', 'sub_index', 'outline_id',
])
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

function priorityColor(ev: string): string {
  if (ev.includes('【重点】')) return 'red'
  if (ev.includes('【一般】')) return 'blue'
  if (ev.includes('【弱】')) return 'default'
  return 'blue'
}

// 涉及角色
const characterFocus = computed<string[]>(() =>
  Array.isArray(planData.value.character_focus) ? planData.value.character_focus : []
)

// 富字段：除标准字段外的所有额外字段（自动遍历，未来 AI 加新字段自动显示）
type FieldEntry = { key: string; label: string; value: string; isArray: boolean }

function formatFieldValue(k: string, v: any): string {
  if (v == null || v === '') return ''
  // character_intents：数组对象 → 中文格式化
  if (k === 'character_intents') {
    const arr = Array.isArray(v) ? v : (typeof v === 'string' ? tryParseJson(v) : [])
    if (Array.isArray(arr)) {
      return arr.map((item: any) => {
        if (typeof item !== 'object' || !item) return String(item)
        const name = item.character || item.name || '?'
        const goal = item.this_chapter_goal || item.goal || ''
        const want = item.immediate_want || item.want || ''
        let line = `【${name}】`
        if (goal) line += `目标：${goal}`
        if (want) line += `；当前欲求：${want}`
        return line
      }).join('\n')
    }
  }
  // shuang_design：对象 → 中文格式化
  if (k === 'shuang_design') {
    const obj = (typeof v === 'object' && v) ? v : tryParseJson(v)
    if (obj && typeof obj === 'object') {
      const parts: string[] = []
      if (obj.info_asymmetry) parts.push(`信息差：${obj.info_asymmetry}`)
      if (obj.shock_level) parts.push(`震惊层级：${obj.shock_level}`)
      if (obj.emotional_rhythm) parts.push(`情绪节奏：${obj.emotional_rhythm}`)
      if (obj.protagonist_style) parts.push(`主角逼格：${obj.protagonist_style}`)
      if (Array.isArray(obj.spectator_layers) && obj.spectator_layers.length) {
        parts.push(`围观分层：${obj.spectator_layers.join(' → ')}`)
      }
      return parts.join('\n') || JSON.stringify(obj)
    }
  }
  // 通用对象
  if (typeof v === 'object') return JSON.stringify(v, null, 2)
  return String(v)
}

function tryParseJson(v: any): any {
  if (typeof v !== 'string') return v
  try { return JSON.parse(v) } catch { return v }
}

const extraFields = computed<FieldEntry[]>(() => {
  const entries: FieldEntry[] = []
  for (const [k, v] of Object.entries(planData.value)) {
    if (SKIP_KEYS.has(k)) continue
    if (v == null || v === '') continue
    const label = FIELD_LABELS[k] || k
    if (Array.isArray(v)) {
      const text = v.map((x: any) => (typeof x === 'object' ? formatFieldValue(k, x) : String(x))).join('；')
      if (text) entries.push({ key: k, label, value: text, isArray: true })
    } else if (typeof v === 'object') {
      const text = formatFieldValue(k, v)
      if (text) entries.push({ key: k, label, value: text, isArray: false })
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

    <!-- 基础信息 -->
    <div v-if="planData.emotional_tone || planData.emotional_arc" class="view-block">
      <div class="view-block-title">💫 情感基调</div>
      <div class="view-block-text">{{ planData.emotional_tone || planData.emotional_arc }}</div>
    </div>
    <div v-if="planData.conflict_type" class="view-block">
      <div class="view-block-title">⚔️ 冲突类型</div>
      <div class="view-block-text">{{ planData.conflict_type }}</div>
    </div>
    <div v-if="planData.rhythm_tag" class="view-block">
      <div class="view-block-title">🎵 节奏标签</div>
      <a-tag :color="planData.rhythm_tag === '小高潮' ? 'red' : 'blue'">{{ planData.rhythm_tag }}</a-tag>
    </div>

    <!-- 剧情摘要 -->
    <div v-if="summary" class="view-block">
      <div class="view-block-title">📝 剧情摘要</div>
      <div class="view-block-text">{{ summary }}</div>
    </div>

    <!-- 关键事件 -->
    <div v-if="keyEvents.length" class="view-block">
      <div class="view-block-title">⚡ 关键事件</div>
      <div class="tag-row">
        <a-tag v-for="(ev, i) in keyEvents" :key="i" :color="priorityColor(ev)">{{ ev }}</a-tag>
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

    <!-- 结尾钩子 -->
    <div v-if="planData.hook" class="view-block hook-block">
      <div class="view-block-title">🪝 结尾钩子</div>
      <div class="view-block-text hook-text">{{ planData.hook }}</div>
    </div>

    <!-- 场景锚点 -->
    <div v-if="planData.scene_anchor" class="view-block scene-anchor-block">
      <div class="view-block-title">📍 场景锚点</div>
      <div class="view-block-text">{{ planData.scene_anchor }}</div>
    </div>

    <!-- 读者钩子 -->
    <div v-if="planData.reader_hook" class="view-block reader-hook-block">
      <div class="view-block-title">🔗 读者钩子</div>
      <div class="view-block-text">{{ planData.reader_hook }}</div>
    </div>

    <!-- 富字段：自动遍历所有额外字段（爽点/角色微意图等） -->
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
.view-block { margin-bottom: 16px; }
.view-block-title { font-size: 13px; font-weight: 600; color: #4D8088; margin-bottom: 8px; }
.view-block-text { font-size: 14px; color: #595959; line-height: 1.7; white-space: pre-wrap; }
.tag-row { display: flex; flex-wrap: wrap; gap: 6px; }
.extra-block { background: #FFFBE6; border-radius: 8px; padding: 12px 14px; border: 1px dashed #FFE58F; }
.extra-grid { columns: 2; column-gap: 10px; }
.extra-item { break-inside: avoid; margin-bottom: 10px; display: flex; flex-direction: column; gap: 2px; }
.extra-label { font-size: 12px; font-weight: 600; color: #AD6800; }
.extra-value { font-size: 13px; color: #595959; line-height: 1.7; word-break: break-word; }
.hook-block { background: #F0F5FF; border-left: 3px solid #597EF7; border-radius: 6px; padding: 10px 12px; }
.hook-text { font-style: italic; color: #2B2B2B; }
.scene-anchor-block { background: #F6FFED; border-left: 3px solid #73D13D; border-radius: 6px; padding: 10px 12px; }
</style>
