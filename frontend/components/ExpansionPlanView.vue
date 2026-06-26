<script setup lang="ts">
	// 章节规划只读详情 — 自动渲染 expansion_plan 全部字段，未来 AI 加新字段无需改这里
	// noModal=true 时只渲染内容（供外部弹窗嵌入使用）
	const props = defineProps<{
	  open: boolean
	  chapterNumber: number
	  chapterTitle?: string
	  plan?: Record<string, any> | null
	  chapterSummary?: string
	  noModal?: boolean
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

function tryParseJson(v: any): any {
  if (typeof v !== 'string') return v
  try { return JSON.parse(v) } catch { return v }
}

const extraFields = computed<FieldEntry[]>(() => {
  const entries: FieldEntry[] = []
  for (const [k, v] of Object.entries(planData.value)) {
    if (SKIP_KEYS.has(k)) continue
    if (v == null || v === '') continue

    // shuang_design：拆成子字段独立展示
    if (k === 'shuang_design') {
      const obj = (typeof v === 'object' && v) ? v : tryParseJson(v)
      if (obj && typeof obj === 'object') {
        const subFields = [
          ['info_asymmetry', '信息差'],
          ['shock_level', '震惊层级'],
          ['spectator_layers', '围观分层'],
          ['emotional_rhythm', '情绪节奏'],
          ['protagonist_style', '主角逼格'],
        ]
        for (const [subKey, subLabel] of subFields) {
          const sv = obj[subKey]
          if (sv == null || sv === '') continue
          const text = Array.isArray(sv) ? sv.join(' → ') : String(sv)
          entries.push({ key: `${k}.${subKey}`, label: subLabel, value: text, isArray: Array.isArray(sv) })
        }
      }
      continue
    }

    // character_intents：拆成每个角色独立一行
    if (k === 'character_intents') {
      const arr = Array.isArray(v) ? v : (typeof v === 'string' ? tryParseJson(v) : [])
      if (Array.isArray(arr)) {
        for (const item of arr) {
          if (typeof item !== 'object' || !item) continue
          const name = item.character || item.name || '?'
          let text = ''
          if (item.this_chapter_goal) text += `目标：${item.this_chapter_goal}`
          if (item.immediate_want) text += text ? `；当前欲求：${item.immediate_want}` : `当前欲求：${item.immediate_want}`
          if (text) entries.push({ key: `${k}.${name}`, label: `角色「${name}」`, value: text, isArray: false })
        }
      }
      continue
    }

    const label = FIELD_LABELS[k] || k
    if (Array.isArray(v)) {
      const text = v.map((x: any) => (typeof x === 'object' ? JSON.stringify(x) : String(x))).join('；')
      if (text) entries.push({ key: k, label, value: text, isArray: true })
    } else if (typeof v === 'object') {
      const text = JSON.stringify(v, null, 2)
      if (text !== '{}') entries.push({ key: k, label, value: text, isArray: false })
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
    v-if="!noModal"
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

    <!-- 富字段 -->
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

  <!-- noModal 模式：仅内容，无弹窗外壳 -->
  <div v-else>
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

    <div v-if="summary" class="view-block">
      <div class="view-block-title">📝 剧情摘要</div>
      <div class="view-block-text">{{ summary }}</div>
    </div>

    <div v-if="keyEvents.length" class="view-block">
      <div class="view-block-title">⚡ 关键事件</div>
      <div class="tag-row">
        <a-tag v-for="(ev, i) in keyEvents" :key="i" :color="priorityColor(ev)">{{ ev }}</a-tag>
      </div>
    </div>

    <div v-if="characterFocus.length" class="view-block">
      <div class="view-block-title">👥 涉及角色</div>
      <div class="tag-row">
        <a-tag v-for="(c, i) in characterFocus" :key="i" color="orange">{{ c }}</a-tag>
      </div>
    </div>

    <div v-if="planData.narrative_goal" class="view-block">
      <div class="view-block-title">🎯 叙事目标</div>
      <div class="view-block-text">{{ planData.narrative_goal }}</div>
    </div>

    <div v-if="planData.hook" class="view-block hook-block">
      <div class="view-block-title">🪝 结尾钩子</div>
      <div class="view-block-text hook-text">{{ planData.hook }}</div>
    </div>

    <div v-if="planData.scene_anchor" class="view-block scene-anchor-block">
      <div class="view-block-title">📍 场景锚点</div>
      <div class="view-block-text">{{ planData.scene_anchor }}</div>
    </div>

    <div v-if="planData.reader_hook" class="view-block reader-hook-block">
      <div class="view-block-title">🔗 读者钩子</div>
      <div class="view-block-text">{{ planData.reader_hook }}</div>
    </div>

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
  </div>
</template>

<style scoped>
.view-subtitle { font-size: 13px; color: #8C8C8C; margin-bottom: 14px; }
.view-block { margin-bottom: 16px; }
.view-block-title { font-size: 13px; font-weight: 600; color: #4D8088; margin-bottom: 8px; }
.view-block-text { font-size: 14px; color: #595959; line-height: 1.7; white-space: pre-wrap; }
.tag-row { display: flex; flex-wrap: wrap; gap: 6px; }
.extra-block { background: #FFFBE6; border-radius: 8px; padding: 12px 14px; border: 1px dashed #FFE58F; }
.extra-grid { display: flex; flex-direction: column; gap: 10px; }
.extra-item { display: flex; flex-direction: column; gap: 2px; }
.extra-label { font-size: 12px; font-weight: 600; color: #AD6800; }
.extra-value { font-size: 13px; color: #595959; line-height: 1.7; word-break: break-word; }
.hook-block { background: #F0F5FF; border-left: 3px solid #597EF7; border-radius: 6px; padding: 10px 12px; }
.hook-text { font-style: italic; color: #2B2B2B; }
.scene-anchor-block { background: #F6FFED; border-left: 3px solid #73D13D; border-radius: 6px; padding: 10px 12px; }
</style>
