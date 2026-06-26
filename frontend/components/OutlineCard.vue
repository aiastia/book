<script setup lang="ts">
// 大纲卡片：按 outline_mode 注入不同的卡片内容
// - one_to_many (1→N)：显示「本卷概览」+ 展开状态Tag + 展开按钮
// - one_to_one (1→1)：显示「大纲梗概」，无展开相关元素
import { reactive, computed } from 'vue'

const props = defineProps<{
  outline: any
  mode: 'one_to_one' | 'one_to_many'
}>()

const emit = defineEmits<{
  (e: 'expand', o: any): void          // 点「展开」按钮（仅 1→N）
  (e: 'toggle-detail', id: number): void  // 展开/收起详情
  (e: 'edit', o: any): void
  (e: 'delete', id: number): void
}>()

const isOneToMany = computed(() => props.mode === 'one_to_many')
const unitLabel = computed(() => isOneToMany.value ? '卷' : '章')

// 卡片内部独立维护展开状态（详情折叠）
const detailOpen = reactive<Record<number, boolean>>({})
function toggleDetail(id: number) {
  detailOpen[id] = !detailOpen[id]
  emit('toggle-detail', id)
}

// ===== 字段解析（与原 outline.vue 逻辑一致）=====
function parseStructure(o: any): any {
  if (o.structure && typeof o.structure === 'object') return o.structure
  if (typeof o.structure === 'string') {
    try { return JSON.parse(o.structure) } catch { return {} }
  }
  return {}
}
function getCharacters(o: any): string[] {
  const s = parseStructure(o)
  const arr = s.characters || o.characters || s.character_focus || []
  return Array.isArray(arr) ? arr : []
}
function getOrganizations(o: any): string[] {
  const s = parseStructure(o)
  const arr = s.organizations || o.organizations || []
  return Array.isArray(arr) ? arr : []
}
function getScenes(o: any): any[] {
  const s = parseStructure(o)
  const arr = s.scenes || o.scenes || []
  return Array.isArray(arr) ? arr : []
}

const FIELD_LABELS: Record<string, string> = {
  shuang_design: '爽点设计', reader_hook: '读者钩子', decision_basis: '决策依据',
  obstacle_type: '障碍类型', hook_type: '钩子类型', chapter_breath: '叙事节奏',
  foreshadow_plant: '伏笔埋设', foreshadow_advance: '伏笔推进',
  character_intents: '角色微意图', scene_anchor: '场景锚点', emotional_arc: '情绪弧线',
  narrative_goal: '叙事目标', conflict_type: '冲突类型', rhythm_tag: '节奏标记',
  character: '角色', this_chapter_goal: '本章目标', immediate_want: '当前欲求',
  new_characters_needed: '需新增角色',
}
const BASE_FIELD_KEYS = new Set([
  'chapter_number', 'title', 'summary', 'scenes', 'characters', 'organizations',
  'key_points', 'emotion', 'goal', 'structure', 'id', 'has_chapters', 'chapter_count',
  'sort_order', 'outline_type',
])
function fieldToText(v: any): string {
  if (v == null) return ''
  if (typeof v === 'string') return v
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  if (Array.isArray(v)) return v.map((x: any) => typeof x === 'object' ? JSON.stringify(x) : String(x)).join('；')
  if (typeof v === 'object') return formatFieldObject(v)
  return String(v)
}

function formatFieldObject(obj: Record<string, any>): string {
  // character_intents 特殊处理
  if (obj.character && (obj.this_chapter_goal || obj.immediate_want)) {
    const parts: string[] = []
    parts.push(`【${obj.character || '?'}】`)
    if (obj.this_chapter_goal) parts.push(`目标：${obj.this_chapter_goal}`)
    if (obj.immediate_want) parts.push(`当前欲求：${obj.immediate_want}`)
    return parts.join('；')
  }
  // 通用：只对已知中文标签的 key 做转换
  const parts: string[] = []
  for (const [k, val] of Object.entries(obj)) {
    const label = FIELD_LABELS[k] || k
    parts.push(`${label}：${fieldToText(val)}`)
  }
  return parts.join('\n')
}

function priorityColor(ev: string): string {
  if (ev.includes('【重点】')) return 'red'
  if (ev.includes('【一般】')) return 'blue'
  if (ev.includes('【弱】')) return 'default'
  return 'blue'
}
function getExtraFields(o: any): Array<{ key: string; label: string; value: string }> {
  const out: Array<{ key: string; label: string; value: string }> = []
  const s = parseStructure(o)
  const sources = [o, s]
  for (const src of sources) {
    if (!src || typeof src !== 'object') continue
    for (const [k, v] of Object.entries(src)) {
      if (BASE_FIELD_KEYS.has(k)) continue
      const text = fieldToText(v)
      if (text && !out.find(x => x.key === k)) out.push({ key: k, label: FIELD_LABELS[k] || k, value: text })
    }
  }
  return out
}
</script>

<template>
  <div class="outline-item">
    <!-- 标题区 -->
    <div class="item-head">
      <span class="item-no">第{{ outline.chapter_number }}{{ unitLabel }}</span>
      <span class="item-title">{{ outline.title || '无标题' }}</span>
      <!-- 1→N：展开状态标签 -->
      <template v-if="isOneToMany">
        <a-tag v-if="outline.has_chapters" color="success" size="small">✓ 展开{{ outline.chapter_count }}章</a-tag>
        <a-tag v-else color="default" size="small">未展开</a-tag>
      </template>
      <div class="item-actions">
        <a-button v-if="isOneToMany" type="link" size="small" @click="emit('expand', outline)">展开</a-button>
        <a-button type="link" size="small" @click="toggleDetail(outline.id)">{{ detailOpen[outline.id] ? '收起详情' : '展开详情' }}</a-button>
      </div>
    </div>

    <!-- 卡片内容 -->
    <div class="item-body">
      <!-- 概览：1→N 显示「本卷概览」，1→1 显示「大纲梗概」（完整显示，不截断） -->
      <div class="content-section">
        <div class="section-label">📝 {{ isOneToMany ? '本卷概览' : '大纲梗概' }}</div>
        <div class="section-text">{{ outline.summary || '' }}</div>
      </div>

      <!-- 叙事目标（默认显示） -->
      <div v-if="outline.goal" class="content-section goal-sec">
        <div class="section-label">🎯 叙事目标</div>
        <div class="section-text">{{ outline.goal }}</div>
      </div>

      <!-- 情感基调（默认显示） -->
      <div v-if="outline.emotion" class="content-section">
        <div class="section-label">💫 情感基调</div>
        <div class="emotion-tag">
          <a-tag size="small" color="orange">{{ outline.emotion }}</a-tag>
        </div>
      </div>

      <!-- ↓↓↓ 以下仅「展开详情」时显示 ↓↓↓ -->

      <div v-if="detailOpen[outline.id] && getCharacters(outline).length" class="content-section chars">
        <div class="section-label">👥 涉及角色（{{ getCharacters(outline).length }}）</div>
        <div class="char-tags">
          <a-tag v-for="(c, i) in getCharacters(outline)" :key="i" color="purple" size="small">{{ c }}</a-tag>
        </div>
      </div>

      <div v-if="detailOpen[outline.id] && getOrganizations(outline).length" class="content-section orgs">
        <div class="section-label">🏛️ 涉及组织（{{ getOrganizations(outline).length }}）</div>
        <div class="char-tags">
          <a-tag v-for="(g, i) in getOrganizations(outline)" :key="i" color="geekblue" size="small">{{ g }}</a-tag>
        </div>
      </div>

      <div v-if="detailOpen[outline.id] && outline.key_points && outline.key_points.length" class="content-section">
        <div class="section-label">💡 情节要点（{{ outline.key_points.length }}）</div>
        <div class="key-points">
          <div v-for="(p, i) in outline.key_points" :key="i" class="kp-item">
            <a-tag :color="priorityColor(typeof p === 'string' ? p : '')" size="small" style="flex-shrink:0;margin-right:6px;">{{ String(i + 1) }}</a-tag>
            <span>{{ typeof p === 'string' ? p : p.content || p.point || p.event || JSON.stringify(p) }}</span>
          </div>
        </div>
      </div>

      <div v-if="detailOpen[outline.id] && getScenes(outline).length" class="content-section">
        <div class="section-label">🎬 场景设定（{{ getScenes(outline).length }}）</div>
        <div class="scene-list">
          <div v-for="(sc, i) in getScenes(outline)" :key="i" class="scene-item">
            <span class="scene-title">{{ sc.scene_title || sc.title || `场景${i + 1}` }}</span>
            <span v-if="sc.scene_desc || sc.desc" class="scene-desc">{{ sc.scene_desc || sc.desc }}</span>
          </div>
        </div>
      </div>

      <div v-if="detailOpen[outline.id] && getExtraFields(outline).length" class="content-section extra-sec">
        <div class="section-label">✨ AI 额外字段（{{ getExtraFields(outline).length }}）</div>
        <div class="extra-list">
          <div v-for="f in getExtraFields(outline)" :key="f.key" class="extra-item">
            <div class="extra-key">{{ f.label }}</div>
            <div class="extra-val">{{ f.value }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 底部操作行 -->
    <div class="item-footer">
      <div class="footer-left">
        <a-button type="text" size="small" @click="emit('edit', outline)">✏️ 编辑</a-button>
      </div>
      <a-button type="text" danger size="small" @click="emit('delete', outline.id)">🗑 删除</a-button>
    </div>
  </div>
</template>

<style scoped>
.outline-item { background: #fff; border-radius: 10px; border: 1px solid #E8E4D9; margin-bottom: 12px; overflow: hidden; }
.item-head { display: flex; align-items: center; gap: 8px; padding: 12px 16px 8px; flex-wrap: wrap; }
.item-no { font-size: 13px; color: #4D8088; font-weight: 600; white-space: nowrap; }
.item-title { font-size: 15px; font-weight: 600; color: #2B2B2B; }
.item-actions { margin-left: auto; display: flex; gap: 4px; }
.item-body { padding: 0 16px 8px; }
.content-section { margin-bottom: 10px; }
.section-label { font-size: 12px; color: #8C8C8C; margin-bottom: 4px; font-weight: 500; }
.section-text { font-size: 14px; color: #595959; line-height: 1.7; }
.goal-sec { background: #F6F8F7; border-radius: 6px; padding: 8px 10px; }
.char-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.key-points { display: flex; flex-direction: column; gap: 6px; }
.kp-item { display: flex; gap: 8px; font-size: 13px; color: #595959; }
.kp-dot { flex-shrink: 0; width: 18px; height: 18px; border-radius: 50%; background: #4D8088; color: #fff; font-size: 11px; display: flex; align-items: center; justify-content: center; }
.scene-list { display: flex; flex-direction: column; gap: 6px; }
.scene-item { display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
.scene-title { font-weight: 500; color: #2B2B2B; }
.scene-desc { color: #8C8C8C; }
.extra-sec { background: #FFFBE6; border-radius: 6px; padding: 8px 10px; border: 1px dashed #FFE58F; }
.extra-list { columns: 2; column-gap: 8px; }
.extra-item { break-inside: avoid; margin-bottom: 8px; display: flex; flex-direction: column; gap: 2px; }
.extra-key { font-size: 12px; color: #AD6800; font-weight: 500; }
.extra-val { font-size: 13px; color: #595959; line-height: 1.6; word-break: break-word; }
.item-footer { display: flex; justify-content: space-between; align-items: center; padding: 8px 16px; border-top: 1px solid #F0EEE8; }
.footer-left { display: flex; gap: 4px; }
</style>
