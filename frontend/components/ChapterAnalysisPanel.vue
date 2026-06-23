<script setup lang="ts">
// 章节分析结果查看面板（含标注联动）
import { apiGet } from '~/composables/useApi'

const props = defineProps<{
  chapterId: number
  chapterNumber: number
  qualityScore?: number | null
}>()

const emit = defineEmits<{ (e: 'close'): void }>()

const { currentProjectId } = useProject()
const msg = useMessage()
const api = useProjectApi()

const visible = ref(false)
const loading = ref(false)
const analysis = ref<any>(null)
const activeTab = ref('overview')

// ===== 标注相关 =====
const chapterContent = ref('')
const annotations = ref<any[]>([])
const annotationSummary = ref<any>({})
const activeAnnotation = ref<any>(null)
const annotationsLoading = ref(false)

// 标注类型配色
const typeMeta: Record<string, { label: string; color: string; icon: string }> = {
  hook: { label: '剧情钩子', color: '#C75B5B', icon: '🎣' },
  foreshadow: { label: '伏笔', color: '#1677FF', icon: '🔮' },
  plot_point: { label: '关键情节', color: '#52A569', icon: '⭐' },
  character_event: { label: '角色事件', color: '#D49A4E', icon: '👤' },
}

// 按类型分组的标注
const annotationGroups = computed(() => {
  const groups: Record<string, any[]> = { hook: [], foreshadow: [], plot_point: [], character_event: [] }
  for (const a of annotations.value) {
    if (a?.type && groups[a.type]) groups[a.type].push(a)
  }
  return Object.entries(groups)
    .filter(([_, items]) => items.length > 0)
    .map(([type, items]) => ({
      type,
      label: typeMeta[type]?.label || type,
      color: typeMeta[type]?.color || '#8C8C8C',
      icon: typeMeta[type]?.icon || '📌',
      items,
    }))
})

// 加载标注数据
async function loadAnnotations() {
  if (!props.chapterId) return
  annotationsLoading.value = true
  try {
    // 并行加载章节内容和标注
    const [ch, annData] = await Promise.all([
      apiGet<any>(`/api/projects/${currentProjectId.value}/chapters/${props.chapterId}`).catch(() => null),
      api.getAnnotations(props.chapterId).catch(() => null),
    ])
    if (ch) chapterContent.value = ch.content || ''
    if (annData) {
      annotations.value = annData.annotations || []
      annotationSummary.value = annData.summary || {}
    }
  } catch (e: any) {
    console.warn('加载标注失败', e)
  } finally {
    annotationsLoading.value = false
  }
}

// 点击标注项
function onAnnotationClick(ann: any) {
  activeAnnotation.value = ann
}

// 点击原文中的标注
function onTextAnnotationSelect(ann: any) {
  activeAnnotation.value = ann
}

// ===== 评分相关 =====
function scoreColor(score: number): string {
  if (score >= 8) return '#52A569'
  if (score >= 6) return '#4D8088'
  if (score >= 4) return '#D49A4E'
  return '#C75B5B'
}

function scoreLevel(score: number): string {
  if (score >= 9) return '优秀'
  if (score >= 7) return '良好'
  if (score >= 5) return '一般'
  if (score >= 3) return '较差'
  return '很差'
}

const scoreLabels: Record<string, string> = {
  overall: '整体质量', pacing: '节奏把控', engagement: '吸引力', coherence: '连贯性',
  writing_quality: '文笔质量', character_depth: '角色塑造',
  dialogue_quality: '对话质量', world_consistency: '世界观一致性',
  plot_logic: '剧情逻辑', attraction: '番茄吸量力', retention: '番茄留存力',
  bookmark_ratio: '番茄追更比潜力',
}

// 从 analysis_report 文本解析评分卡片（自动支持任意维度数，含番茄维度）
const reportScores = computed<Array<{ label: string; value: number }>>(() => {
  const report = analysis.value?.analysis_report || ''
  const items: Array<{ label: string; value: number }> = []
  const block = report.match(/【整体评分】[\s\S]*?(?=\n【|\n\s*\n|$)/)
  if (block) {
    for (const line of block[0].split('\n')) {
      if (line.includes('评分理由')) continue
      const m = line.match(/^\s*([^:：]+)[:：]\s*([\d.]+)/)
      if (m) {
        const label = m[1].trim()
        const value = parseFloat(m[2])
        if (!isNaN(value) && label) items.push({ label, value })
      }
    }
  }
  return items
})

// 评分理由
const scoreJustification = computed(() => {
  const report = analysis.value?.analysis_report || ''
  const m = report.match(/评分理由[:：]\s*(.+)/)
  if (m) return m[1].trim()
  return analysis.value?.quality_scores?.score_justification || ''
})

const useReportScores = computed(() => reportScores.value.length > 0)

// 降级：从 quality_scores 构造评分卡（排除 score_justification）
const qualityScoreCards = computed(() => {
  const qs = analysis.value?.quality_scores || {}
  return Object.entries(qs)
    .filter(([k, v]) => k !== 'score_justification' && typeof v === 'number')
    .map(([k, v]) => ({ key: k, label: scoreLabels[k] || k, value: v as number }))
})

function pacingText(p: string): string {
  return { fast: '快速', medium: '中等', slow: '缓慢' }[p] || p || ''
}

function survivalText(s: string): string {
  return { '存活': '存活', '死亡': '死亡', '失踪': '失踪', '退隐': '退隐' }[s] || s || ''
}

// ===== 数据解析 =====
function parseHooks(data: any): Array<{ type: string; content: string }> {
  if (!data) return []
  if (Array.isArray(data)) return data.map(h => ({ type: h.type || '', content: h.content || h.text || h.detail || '' }))
  if (typeof data === 'object') {
    return Object.entries(data)
      .filter(([_, v]) => v)
      .map(([type, content]) => ({
        type: { suspense: '悬念钩子', emotional: '情感钩子', conflict: '冲突钩子', cognitive: '认知钩子' }[type] || type,
        content: String(content),
      }))
  }
  return []
}

function parseForeshadows(data: any[]): Array<{ title: string; detail: string; type: string }> {
  if (!Array.isArray(data)) return []
  return data.map(f => ({
    title: f.title || '',
    detail: f.detail || f.content || '',
    type: f.type || '',
  }))
}

function parseConflicts(data: any[]): Array<{ type: string; parties: string; intensity: number; progress: string }> {
  if (!Array.isArray(data)) return []
  return data.map(c => ({
    type: c.type || '',
    parties: Array.isArray(c.parties) ? c.parties.join(' vs ') : (c.parties || ''),
    intensity: c.intensity || 0,
    progress: c.progress || '',
  }))
}

function parseCharacterStates(data: any[]): Array<{ name: string; mental: string; relation: string; survival: string; ability: string }> {
  if (!Array.isArray(data)) return []
  return data.map(c => ({
    name: c.character_name || c.name || '',
    mental: c.mental_change || c.psychological_change || '',
    relation: c.relation_change || '',
    survival: c.survival_status || '',
    ability: c.ability_change || '',
  }))
}

function parseSuggestions(data: any[]): string[] {
  if (!Array.isArray(data)) return []
  return data.map(s => typeof s === 'string' ? s : s.content || s.text || '')
}

function parseKeyPoints(data: any[]): string[] {
  if (!Array.isArray(data)) return []
  return data.map(p => typeof p === 'string' ? p : p.content || p.text || '')
}

function parseEmotionCurve(data: any[]): Array<{ point: string; emotion: string; intensity: number }> {
  if (!Array.isArray(data)) return []
  return data.map(e => ({
    point: e.point || e.label || '',
    emotion: e.emotion || '',
    intensity: e.intensity || e.value || 0,
  }))
}

// ===== 打开/关闭 =====
async function open() {
  visible.value = true
  loading.value = true
  analysis.value = null
  chapterContent.value = ''
  annotations.value = []
  activeAnnotation.value = null
  activeTab.value = 'overview'
  try {
    const data = await apiGet<any>(`/api/projects/${currentProjectId.value}/analyses/${props.chapterNumber}`).catch(() => null)
    if (data && !data.detail) analysis.value = data
  } catch (e: any) {
    msg.error('加载分析失败：' + formatError(e))
  } finally {
    loading.value = false
  }
}

// 切换到标注 tab 时加载数据
watch(activeTab, (tab) => {
  if (tab === 'annotations' && !chapterContent.value && !annotationsLoading.value) {
    loadAnnotations()
  }
})

// 触发分析（异步后台任务 + 右下角面板进度）
const analyzing = ref(false)
const { trackTask } = useBackgroundTasks()

async function onAnalyze() {
  analyzing.value = true
  try {
    const r = await api.triggerAnalysisAsync(props.chapterId)
    if (r?.task_id) {
      trackTask({ id: r.task_id, task_type: 'chapter_analyze', title: `分析第${props.chapterNumber}章`, status: 'pending' })
      msg.success(`分析任务已提交，可在右下角查看进度`)
      // 关闭面板，交给右下角面板跟进（用户可重新打开查看结果）
      visible.value = false
      // 后台轮询，完成后刷新数据（不阻塞 UI）
      pollAnalysisAndRefresh(r.task_id)
    } else {
      msg.info('该章节已在分析中或无需分析')
    }
  } catch (e: any) {
    msg.error('提交分析失败：' + formatError(e))
  } finally {
    analyzing.value = false
  }
}

async function pollAnalysisAndRefresh(taskId: number) {
  const maxAttempts = 300
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(r => setTimeout(r, 2000))
    try {
      const t = await apiGet<any>(`/api/tasks/${taskId}`)
      if (t.status === 'completed') {
        const data = await apiGet<any>(`/api/projects/${currentProjectId.value}/analyses/${props.chapterNumber}`).catch(() => null)
        if (data && !data.detail) analysis.value = data
        if (activeTab.value === 'annotations') await loadAnnotations()
        msg.success(`第${props.chapterNumber}章分析完成`)
        return
      }
      if (t.status === 'failed' || t.status === 'cancelled') {
        msg.error(`第${props.chapterNumber}章分析失败：${t.error || ''}`)
        return
      }
    } catch { /* 忽略单次轮询错误 */ }
  }
}

defineExpose({ open })
</script>

<template>
  <a-modal
    v-model:open="visible"
    :title="`📊 第${chapterNumber}章 · 剧情分析报告`"
    width="960px"
    :footer="null"
    :body-style="{ padding: '12px 20px' }"
    @cancel="emit('close')"
  >
    <!-- 加载中 -->
    <div v-if="loading" class="state-wrap">
      <a-spin size="large" />
      <div class="state-text">加载分析数据...</div>
    </div>

    <!-- 无分析数据 -->
    <div v-else-if="!analysis" class="state-wrap">
      <div class="state-icon">📊</div>
      <div class="state-text">该章节尚未进行剧情分析</div>
      <a-button type="primary" :loading="analyzing" @click="onAnalyze">
        {{ analyzing ? '分析中...' : '开始分析' }}
      </a-button>
    </div>

    <!-- 分析结果 -->
    <template v-else>
      <a-tabs v-model:activeKey="activeTab" size="small">
        <!-- Tab 1: 总览 -->
        <a-tab-pane key="overview" tab="📋 总览">
          <!-- 评分卡片：优先用报告解析（自动支持任意维度，含番茄维度），降级 quality_scores -->
          <div v-if="useReportScores" class="score-grid">
            <div v-for="(s, i) in reportScores" :key="i" class="score-card"
                 :class="{ highlight: /整体|overall/i.test(s.label) }">
              <div class="score-label">{{ s.label }}</div>
              <div class="score-num" :style="{ color: scoreColor(s.value) }">{{ s.value.toFixed(1) }}</div>
              <div v-if="/整体|overall/i.test(s.label)" class="score-level" :style="{ color: scoreColor(s.value) }">{{ scoreLevel(s.value) }}</div>
            </div>
          </div>
          <div v-else-if="qualityScoreCards.length" class="score-grid">
            <div v-for="s in qualityScoreCards" :key="s.key" class="score-card"
                 :class="{ highlight: s.key === 'overall' }">
              <div class="score-label">{{ s.label }}</div>
              <div class="score-num" :style="{ color: scoreColor(s.value) }">{{ s.value }}</div>
              <div v-if="s.key === 'overall'" class="score-level" :style="{ color: scoreColor(s.value) }">{{ scoreLevel(s.value) }}</div>
            </div>
          </div>

          <!-- 评分理由 -->
          <div v-if="scoreJustification" class="section-block justify">
            <div class="section-title">📝 评分理由</div>
            <div class="justify-text">{{ scoreJustification }}</div>
          </div>

          <!-- 分析摘要 -->
          <div v-if="analysis.analysis_report" class="section-block">
            <div class="section-title">📄 分析摘要</div>
            <pre class="report-pre">{{ analysis.analysis_report }}</pre>
          </div>
          <div class="info-bar">
            <span v-if="analysis.plot_stage" class="info-chip">
              <span class="info-chip-label">剧情阶段</span>
              <a-tag color="blue">{{ analysis.plot_stage }}</a-tag>
            </span>
            <span v-if="analysis.pacing" class="info-chip">
              <span class="info-chip-label">节奏</span>
              <a-tag color="cyan">{{ pacingText(analysis.pacing) }}</a-tag>
            </span>
            <span v-if="analysis.dialogue_ratio" class="info-chip">
              <span class="info-chip-label">对话占比</span>
              <span>{{ ((analysis.dialogue_ratio || 0) * 100).toFixed(0) }}%</span>
            </span>
            <span v-if="analysis.description_ratio" class="info-chip">
              <span class="info-chip-label">描写占比</span>
              <span>{{ ((analysis.description_ratio || 0) * 100).toFixed(0) }}%</span>
            </span>
          </div>
          <div v-if="analysis.conflict_types?.length" class="info-bar">
            <span class="info-chip-label">冲突类型</span>
            <a-tag v-for="t in analysis.conflict_types" :key="t" color="red">{{ t }}</a-tag>
          </div>
          <div v-if="parseSuggestions(analysis.suggestions).length" class="section-block">
            <div class="section-title">💡 改进建议</div>
            <div class="suggestion-list">
              <div v-for="(s, i) in parseSuggestions(analysis.suggestions)" :key="i" class="suggestion-item">
                <span class="suggestion-badge">{{ i + 1 }}</span>
                <span>{{ s }}</span>
              </div>
            </div>
          </div>
        </a-tab-pane>

        <!-- Tab 2: 钩子 -->
        <a-tab-pane key="hooks">
          <template #tab>🎣 钩子 <a-badge :count="parseHooks(analysis.hooks).length" :number-style="{ backgroundColor: '#C75B5B', fontSize: '11px' }" /></template>
          <div v-if="parseHooks(analysis.hooks).length" class="data-list">
            <div v-for="(h, i) in parseHooks(analysis.hooks)" :key="i" class="data-card">
              <a-tag color="blue">{{ h.type }}</a-tag>
              <div class="data-text">{{ h.content }}</div>
            </div>
          </div>
          <a-empty v-else description="暂无钩子数据" />
        </a-tab-pane>

        <!-- Tab 3: 伏笔 -->
        <a-tab-pane key="foreshadows">
          <template #tab>🔮 伏笔 <a-badge :count="parseForeshadows(analysis.foreshadows).length" :number-style="{ backgroundColor: '#1677FF', fontSize: '11px' }" /></template>
          <div v-if="parseForeshadows(analysis.foreshadows).length" class="data-list">
            <div v-for="(f, i) in parseForeshadows(analysis.foreshadows)" :key="i" class="data-card">
              <div class="data-card-top">
                <span v-if="f.title" class="data-title">{{ f.title }}</span>
                <a-tag v-if="f.type" :color="f.type === 'planted' ? 'green' : f.type === 'resolved' ? 'purple' : 'blue'">
                  {{ f.type === 'planted' ? '已埋设' : f.type === 'resolved' ? '已回收' : f.type }}
                </a-tag>
              </div>
              <div v-if="f.detail" class="data-text">{{ f.detail }}</div>
            </div>
          </div>
          <a-empty v-else description="暂无伏笔数据" />
        </a-tab-pane>

        <!-- Tab 4: 冲突 -->
        <a-tab-pane key="conflicts">
          <template #tab>⚡ 冲突 <a-badge :count="parseConflicts(analysis.conflicts).length" :number-style="{ backgroundColor: '#D49A4E', fontSize: '11px' }" /></template>
          <div v-if="parseConflicts(analysis.conflicts).length" class="data-list">
            <div v-for="(c, i) in parseConflicts(analysis.conflicts)" :key="i" class="data-card">
              <div class="data-card-top">
                <a-tag v-if="c.type" color="red">{{ c.type }}</a-tag>
                <a-tag v-if="c.intensity" color="orange">强度 {{ c.intensity }}/10</a-tag>
              </div>
              <div v-if="c.parties" class="data-meta">相关方：{{ c.parties }}</div>
              <div v-if="c.progress" class="data-text">{{ c.progress }}</div>
            </div>
          </div>
          <a-empty v-else description="暂无冲突数据" />
        </a-tab-pane>

        <!-- Tab 5: 角色 -->
        <a-tab-pane key="characters">
          <template #tab>👤 角色 <a-badge :count="parseCharacterStates(analysis.character_states).length" :number-style="{ backgroundColor: '#D49A4E', fontSize: '11px' }" /></template>
          <div v-if="parseCharacterStates(analysis.character_states).length" class="data-list">
            <div v-for="(c, i) in parseCharacterStates(analysis.character_states)" :key="i" class="data-card">
              <div class="data-card-top">
                <span class="data-title">{{ c.name }}</span>
                <a-tag v-if="c.survival" :color="c.survival === '死亡' ? 'red' : c.survival === '失踪' ? 'orange' : 'green'">
                  {{ survivalText(c.survival) }}
                </a-tag>
              </div>
              <div v-if="c.mental" class="data-row"><span class="data-row-label">心理变化</span>{{ c.mental }}</div>
              <div v-if="c.relation" class="data-row"><span class="data-row-label">关系变化</span>{{ c.relation }}</div>
              <div v-if="c.ability" class="data-row"><span class="data-row-label">能力变化</span>{{ c.ability }}</div>
            </div>
          </div>
          <a-empty v-else description="暂无角色状态数据" />
        </a-tab-pane>

        <!-- Tab 6: 情感 -->
        <a-tab-pane key="emotion" tab="🎭 情感">
          <div v-if="analysis.emotional_curve" class="emotion-section">
            <div v-if="analysis.emotional_curve.dominant_emotion" class="info-bar">
              <span class="info-chip">
                <span class="info-chip-label">主导情感</span>
                <a-tag color="blue">{{ analysis.emotional_curve.dominant_emotion }}</a-tag>
              </span>
            </div>
            <div v-if="analysis.emotional_curve.arc_summary" class="arc-block">
              <div class="arc-label">情感弧线</div>
              <div class="arc-text">{{ analysis.emotional_curve.arc_summary }}</div>
            </div>
          </div>
          <div v-if="parseEmotionCurve(analysis.emotion_curve).length" class="emotion-list">
            <div v-for="(e, i) in parseEmotionCurve(analysis.emotion_curve)" :key="i" class="emotion-row">
              <span class="emotion-point">{{ e.point }}</span>
              <span class="emotion-name">{{ e.emotion }}</span>
              <a-progress :percent="e.intensity * 10" :stroke-color="scoreColor(e.intensity)" size="small" style="flex: 1" />
            </div>
          </div>
          <a-empty v-if="!analysis.emotional_curve && !analysis.emotion_curve?.length" description="暂无情感数据" />
        </a-tab-pane>

        <!-- Tab 7: 关键情节 -->
        <a-tab-pane key="plot_points">
          <template #tab>⭐ 关键情节 <a-badge :count="parseKeyPoints(analysis.key_plot_points).length" :number-style="{ backgroundColor: '#52A569', fontSize: '11px' }" /></template>
          <div v-if="parseKeyPoints(analysis.key_plot_points).length" class="data-list">
            <div v-for="(p, i) in parseKeyPoints(analysis.key_plot_points)" :key="i" class="data-card">
              <div class="data-text">{{ p }}</div>
            </div>
          </div>
          <a-empty v-else description="暂无关键情节数据" />
        </a-tab-pane>

        <!-- Tab 8: 本章标注 -->
        <a-tab-pane key="annotations">
          <template #tab>
            📌 本章标注
            <a-badge v-if="annotationSummary.total" :count="annotationSummary.total" :number-style="{ backgroundColor: '#4D8088', fontSize: '11px' }" />
          </template>
          <div v-if="annotationsLoading" class="state-wrap" style="padding: 40px 0">
            <a-spin />
            <div class="state-text">加载标注...</div>
          </div>
          <div v-else class="annot-layout">
            <!-- 左侧：原文（带标注高亮） -->
            <div class="annot-content">
              <div class="annot-content-header">
                <span>原文</span>
                <span v-if="annotationSummary.total" class="annot-summary">
                  <span v-for="g in annotationGroups" :key="g.type" :style="{ color: g.color }">
                    {{ g.icon }} {{ g.items.length }}
                  </span>
                </span>
              </div>
              <div class="annot-content-body">
                <ClientOnly>
                  <AnnotatedText
                    v-if="chapterContent"
                    :content="chapterContent"
                    :annotations="annotations"
                    :active-id="activeAnnotation ? `${activeAnnotation.type}-${activeAnnotation.position}` : null"
                    @select="onTextAnnotationSelect"
                  />
                  <div v-else class="no-content">暂无章节内容</div>
                </ClientOnly>
              </div>
            </div>

            <!-- 右侧：标注列表 -->
            <div class="annot-sidebar">
              <div class="annot-sidebar-title">本章标注</div>
              <div v-if="annotationGroups.length === 0" class="annot-empty">暂无标注</div>
              <div v-for="g in annotationGroups" :key="g.type" class="annot-group">
                <div class="annot-group-title" :style="{ color: g.color }">
                  {{ g.icon }} {{ g.label }}（{{ g.items.length }}）
                </div>
                <div
                  v-for="(a, i) in g.items"
                  :key="i"
                  class="annot-item"
                  :class="{ active: activeAnnotation === a }"
                  :style="{ borderLeftColor: g.color }"
                  @click="onAnnotationClick(a)"
                >
                  <div class="annot-item-title">{{ a.title }}</div>
                  <div class="annot-item-content">{{ a.content }}</div>
                </div>
              </div>
            </div>
          </div>
        </a-tab-pane>
      </a-tabs>

      <!-- 底部 -->
      <div class="panel-footer">
        <a-button :loading="analyzing" @click="onAnalyze">
          {{ analyzing ? '提交中...' : '🔄 重新分析' }}
        </a-button>
      </div>
    </template>
  </a-modal>
</template>

<style scoped>
.state-wrap { text-align: center; padding: 60px 0; }
.state-icon { font-size: 48px; margin-bottom: 16px; }
.state-text { color: #8C8C8C; margin-bottom: 16px; font-size: 14px; }

/* 评分 */
.score-grid { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; }
.score-card { background: #FAFAF7; border: 1px solid #E8E4DC; border-radius: 8px; padding: 10px 14px; min-width: 90px; text-align: center; }
.score-card.highlight { background: linear-gradient(135deg, #F0F5F5, #EAF0F1); border-color: #B8CDD1; min-width: 110px; }
.score-label { font-size: 11px; color: #8C8C8C; margin-bottom: 2px; }
.score-num { font-size: 22px; font-weight: 700; line-height: 1.2; }
.score-level { font-size: 11px; font-weight: 600; margin-top: 2px; }

/* 信息条 */
.info-bar { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }
.info-chip { display: flex; align-items: center; gap: 4px; }
.info-chip-label { font-size: 13px; color: #8C8C8C; }

/* 区块 */
.section-block { margin-top: 20px; }
.section-title { font-size: 15px; font-weight: 600; color: #4D8088; margin-bottom: 10px; }

/* 评分理由 */
.section-block.justify { background: #EAF3F1; border: 1px solid #C8DDD9; border-radius: 8px; padding: 12px 14px; }
.justify-text { font-size: 13px; color: #595959; line-height: 1.8; white-space: pre-wrap; }

/* 分析摘要报告 */
.report-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.8;
  color: #595959;
}
.suggestion-list { display: flex; flex-direction: column; gap: 8px; }
.suggestion-item { display: flex; gap: 8px; align-items: flex-start; font-size: 14px; color: #595959; line-height: 1.5; }
.suggestion-badge { background: #4D8088; color: #fff; font-size: 11px; font-weight: 700; width: 20px; height: 20px; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex-shrink: 0; margin-top: 2px; }

/* 数据卡片 */
.data-list { display: flex; flex-direction: column; gap: 8px; }
.data-card { background: #FAFAF7; border: 1px solid #E8E4DC; border-radius: 8px; padding: 10px 14px; }
.data-card-top { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }
.data-title { font-size: 14px; font-weight: 600; color: #2B2B2B; }
.data-text { font-size: 14px; color: #2B2B2B; line-height: 1.6; }
.data-meta { font-size: 13px; color: #8C8C8C; margin-top: 4px; }
.data-row { font-size: 13px; color: #595959; margin-top: 4px; }
.data-row-label { color: #8C8C8C; margin-right: 6px; }

/* 情感 */
.emotion-section { margin-bottom: 16px; }
.arc-block { background: #FAFAF7; border-radius: 8px; padding: 12px; margin-top: 10px; }
.arc-label { font-size: 13px; color: #8C8C8C; margin-bottom: 6px; }
.arc-text { font-size: 14px; color: #595959; line-height: 1.6; }
.emotion-list { display: flex; flex-direction: column; gap: 8px; }
.emotion-row { display: flex; align-items: center; gap: 10px; }
.emotion-point { font-size: 13px; color: #8C8C8C; min-width: 60px; }
.emotion-name { font-size: 13px; color: #595959; min-width: 40px; }

/* 标注布局 */
.annot-layout {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: 14px;
  height: calc(100vh - 240px);
  min-height: 400px;
}
.annot-content {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid #E8E4DC;
  border-radius: 8px;
}
.annot-content-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  background: #F8F6F1;
  border-bottom: 1px solid #E8E4DC;
  font-size: 13px;
  font-weight: 600;
  color: #4D8088;
}
.annot-summary { display: flex; gap: 10px; font-size: 12px; }
.annot-content-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  background: #fff;
  font-size: 15px;
  line-height: 2;
}
.no-content { color: #8C8C8C; text-align: center; padding: 40px 0; }

/* 标注侧栏 */
.annot-sidebar {
  overflow-y: auto;
  border: 1px solid #E8E4DC;
  border-radius: 8px;
  background: #fff;
  padding: 10px;
}
.annot-sidebar-title {
  font-size: 13px;
  font-weight: 600;
  color: #4D8088;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid #F0EDE6;
}
.annot-empty { font-size: 13px; color: #8C8C8C; text-align: center; padding: 20px 0; }
.annot-group { margin-bottom: 12px; }
.annot-group-title { font-size: 12px; font-weight: 600; margin-bottom: 6px; }
.annot-item {
  padding: 8px 10px;
  background: #FAFAF7;
  border-radius: 6px;
  border-left: 3px solid #B5C7CB;
  margin-bottom: 6px;
  cursor: pointer;
  transition: all .15s;
}
.annot-item:hover { background: #F0EDE6; }
.annot-item.active { background: #EAF0F1; border-left-width: 4px; }
.annot-item-title { font-size: 12px; font-weight: 600; color: #2B2B2B; margin-bottom: 3px; }
.annot-item-content { font-size: 12px; color: #595959; line-height: 1.5; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; }

/* 底部 */
.panel-footer { display: flex; justify-content: flex-end; margin-top: 16px; padding-top: 12px; border-top: 1px solid #E8E4DC; }
</style>
