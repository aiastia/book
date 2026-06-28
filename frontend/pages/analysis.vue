<script setup lang="ts">
// 剧情分析：按章节展示分析维度，对标 MuMuAINovel Tab 布局

import { API } from '~/composables/api'
import { useProject } from '~/composables/useProject'
import type { PlotAnalysis } from '~/composables/api/types'
useHead({ title: '剧情分析 — 墨语' })
const { currentProjectId } = useProject()
if (!currentProjectId.value) await navigateTo('/books')
const msg = useMessage()
const { data: analyses, refresh: refresh } = await useFetch<PlotAnalysis[]>(() => `/api/projects/${currentProjectId.value}/analyses`)
const { data: chapters } = await API.chapter.getAnalyses()

// 选择章节查看详情
const selectedChapter = ref<number | null>(null)
const detail = ref<any>(null)
const loading = ref(false)
const activeTab = ref('overview')
// 视图模式：annotation（正文+标注，对标 MuMu）/ report（详细报告）
const viewMode = ref<'annotation' | 'report'>('annotation')
// 正文 + 标注数据
const chapterContent = ref('')
const annotations = ref<any[]>([])
const annotationSummary = ref<any>({})
const activeAnnotation = ref<any>(null)
const showAnnotations = ref(true)
const { groupAnnotations } = useAnnotationTypes()

async function viewDetail(chapterNumber: number) {
  selectedChapter.value = chapterNumber
  loading.value = true
  detail.value = null
  chapterContent.value = ''
  annotations.value = []
  annotationSummary.value = {}
  activeAnnotation.value = null
  activeTab.value = 'overview'
  // 并行加载：分析报告 + 章节正文 + 标注
  const cid = chapterIdByNumber(chapterNumber)
  try {
    const [r, ch, ann] = await Promise.all([
      API.chapter.getAnalysis(chapterNumber).catch(() => null),
      cid ? API.chapter.get(cid).catch(() => null) : Promise.resolve(null),
      cid ? API.chapter.getAnnotations(cid).catch(() => null) : Promise.resolve(null),
    ])
    detail.value = r
    if (ch) chapterContent.value = ch.content || ''
    if (ann) {
      annotations.value = ann.annotations || []
      annotationSummary.value = ann.summary || {}
    }
  } catch (e: any) {
    const status = e?.response?.status || e?.status
    if (status === 404) detail.value = null
    else msg.error('加载分析失败：' + formatError(e))
  } finally { loading.value = false }
}

// 标注分组
const annotationGroups = computed(() => groupAnnotations(annotations.value))
// 已定位的标注（用于正文高亮，只显示能在正文找到位置的）
const locatedAnnotations = computed(() =>
  (annotations.value || []).filter(a => a.located !== false && a.length > 0)
)
// 未定位标注数（侧边栏提示）
const unlocatedCount = computed(() =>
  (annotations.value || []).filter(a => a.located === false).length
)

const analysisMap = computed(() => {
  const m: Record<number, any> = {}
  for (const a of (analyses.value||[])) {
    if (a && (a.quality_scores || a.plot_stage)) {
      m[a.chapter_number] = a
    }
  }
  return m
})

// 评分维度中文映射
const scoreLabels: Record<string, string> = {
  overall: '整体质量', pacing: '节奏把控', engagement: '吸引力', coherence: '连贯性',
  writing_quality: '文笔质量', character_depth: '角色塑造',
  dialogue_quality: '对话质量', world_consistency: '世界观一致性',
  plot_logic: '剧情逻辑', attraction: '番茄吸量力', retention: '番茄留存力',
  bookmark_ratio: '番茄追更比潜力',
}

// 从 analysis_report 文本解析评分卡片（自动支持任意维度数，含番茄维度）
const reportScores = computed<Array<{ label: string; value: number }>>(() => {
  const report = detail.value?.analysis_report || ''
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

// 评分理由（从报告文本或 quality_scores 提取，分号转行更易读）
const scoreJustification = computed(() => {
  const report = detail.value?.analysis_report || ''
  // 多行匹配：评分理由后到下一个【标题】或空行
  const m = report.match(/评分理由[:：][\s\S]*?(?=\n【|\n\s*\n|$)/)
  let text = ''
  if (m) {
    // 去掉 "评分理由:" 前缀和多余缩进
    text = m[0].replace(/评分理由[:：]\s*/, '').replace(/^\s+/gm, '').trim()
  } else {
    text = detail.value?.quality_scores?.score_justification || ''
  }
  // 历史数据分号兜底转行
  return text.replace(/；/g, '\n').replace(/;/g, '\n')
})

// 是否使用报告解析的评分卡（有 report 优先用，否则降级 quality_scores）
const useReportScores = computed(() => reportScores.value.length > 0)

// 降级用：从 quality_scores 构造的评分卡（排除 overall 单独显示，排除 score_justification）
const qualityScoreCards = computed(() => {
  const qs = detail.value?.quality_scores || {}
  return Object.entries(qs)
    .filter(([k, v]) => k !== 'score_justification' && typeof v === 'number')
    .map(([k, v]) => ({ key: k, label: scoreLabels[k] || k, value: v as number }))
})

// 统一评分数据源（reportScores 优先，降级 qualityScoreCards）
const allScoreCards = computed<Array<{ key?: string; label: string; value: number }>>(() => {
  if (useReportScores.value) {
    return reportScores.value.map(s => {
      // 反查 key（用于分组判断）
      const key = Object.entries(scoreLabels).find(([, label]) => label === s.label)?.[0] || ''
      return { key, label: s.label, value: s.value }
    })
  }
  return qualityScoreCards.value
})

// 评分分组（按用户要求布局）：整体质量 / 核心三维 / 番茄三维 / 其他维度
const CORE_KEYS = ['pacing', 'engagement', 'coherence']
const TOMATO_KEYS = ['attraction', 'retention', 'bookmark_ratio']
const overallCard = computed(() => {
  const c = allScoreCards.value.find(s => s.key === 'overall' || /整体|overall/i.test(s.label))
  return c || null
})
const coreCards = computed(() => allScoreCards.value.filter(s => CORE_KEYS.includes(s.key || '')))
const tomatoCards = computed(() => allScoreCards.value.filter(s => TOMATO_KEYS.includes(s.key || '')))
const otherCards = computed(() => allScoreCards.value.filter(s =>
  s.key !== 'overall' && !CORE_KEYS.includes(s.key || '') && !TOMATO_KEYS.includes(s.key || '')
))

function scoreColor(v: number): string {
  if (v >= 8) return '#52A569'
  if (v >= 6) return '#4D8088'
  if (v >= 4) return '#D49A4E'
  return '#C75B5B'
}

function scoreLevel(v: number): string {
  if (v >= 9) return '优秀'
  if (v >= 7) return '良好'
  if (v >= 5) return '一般'
  if (v >= 3) return '较差'
  return '很差'
}

const PACING_MAP: Record<string, string> = {
  fast: '快速', slow: '缓慢', medium: '中等',
  varied: '多变', mixed: '多变', balanced: '均衡',
  rapid: '急促', steady: '稳健', gradual: '渐进',
  tense: '紧张', relaxed: '舒缓', dynamic: '富有张力',
}
function pacingText(p: string): string {
  if (!p) return ''
  const key = String(p).toLowerCase().trim()
  return PACING_MAP[key] || p
}

// 手动触发分析（异步后台任务 + 右下角面板进度）
const analyzing = ref(false)
const analyzingAll = ref(false)
const { trackTask } = useBackgroundTasks()

async function analyzeChapter(chapterId: number, chapterNumber: number) {
  analyzing.value = true
  try {
    const r = await API.chapter.triggerAnalysis(chapterId)
    if (r?.task_id) {
      trackTask({ id: r.task_id, task_type: 'chapter_analyze', title: `分析第${chapterNumber}章`, status: 'pending' })
      msg.success(`第${chapterNumber}章分析任务已提交，可在右下角查看进度`)
      // 轮询任务状态，完成后刷新
      pollAnalysisTask(r.task_id, chapterNumber)
    } else {
      msg.info('该章节已在分析中或无需分析')
    }
  } catch (e: any) {
    const status = e?.response?.status || e?.status
    if (status === 400) {
      msg.error('分析失败：章节内容过少，无法分析')
    } else {
      msg.error('提交分析失败：' + formatError(e))
    }
  } finally {
    analyzing.value = false
  }
}

async function pollAnalysisTask(taskId: number, chapterNumber: number, onDone?: () => void) {
  const maxAttempts = 300 // 约 10 分钟
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(r => setTimeout(r, 2000))
    try {
      const t = await API.task.getStatus(taskId)
      if (t.status === 'completed') {
        await refresh()
        await viewDetail(chapterNumber)
        msg.success(`第${chapterNumber}章分析完成`)
        onDone?.()
        return
      }
      if (t.status === 'failed' || t.status === 'cancelled') {
        msg.error(`第${chapterNumber}章分析失败：${t.error || ''}`)
        onDone?.()
        return
      }
    } catch { /* 忽略单次轮询错误，继续 */ }
  }
}

async function analyzeAll() {
  if (!await msg.confirm('将分析所有未分析的章节，可能需要较长时间。确认开始？')) return
  analyzingAll.value = true
  try {
    const r = await API.chapter.analyzeAll()
    if (r?.task_id) {
      trackTask({ id: r.task_id, task_type: 'chapter_batch_analyze', title: '批量剧情分析', status: 'pending' })
      msg.success('批量分析任务已提交，可在右下角查看进度')
      // 完成后刷新
      pollBatchAnalysisTask(r.task_id)
    } else {
      msg.info('所有章节都已分析过')
    }
  } catch (e: any) {
    msg.error('批量分析失败：' + formatError(e))
  } finally {
    analyzingAll.value = false
  }
}

async function pollBatchAnalysisTask(taskId: number) {
  const maxAttempts = 600
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(r => setTimeout(r, 3000))
    try {
      const t = await API.task.getStatus(taskId)
      if (t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled') {
        await refresh()
        if (selectedChapter.value) await viewDetail(selectedChapter.value)
        return
      }
    } catch { /* 忽略单次轮询错误 */ }
  }
}

function chapterIdByNumber(num: number): number | null {
  const c = (chapters.value || []).find((x: any) => x.chapter_number === num)
  return c?.id || null
}

// ===== 章节导航（上一章/下一章）=====
const sortedChapterNumbers = computed(() =>
  [...(chapters.value || [])].map((c: any) => c.chapter_number).sort((a, b) => a - b)
)

const navInfo = computed(() => {
  if (!selectedChapter.value) return { hasPrev: false, hasNext: false }
  const nums = sortedChapterNumbers.value
  const idx = nums.indexOf(selectedChapter.value)
  return {
    hasPrev: idx > 0,
    hasNext: idx >= 0 && idx < nums.length - 1,
    prevNum: idx > 0 ? nums[idx - 1] : null,
    nextNum: idx >= 0 && idx < nums.length - 1 ? nums[idx + 1] : null,
  }
})

function goPrevChapter() {
  if (navInfo.value.hasPrev && navInfo.value.prevNum != null) viewDetail(navInfo.value.prevNum)
}
function goNextChapter() {
  if (navInfo.value.hasNext && navInfo.value.nextNum != null) viewDetail(navInfo.value.nextNum)
}

const unanalyzedChapters = computed(() => {
  const analyzedNums = new Set((analyses.value || []).map((a: any) => a.chapter_number))
  return (chapters.value || []).filter((c: any) =>
    c.content && c.content.length > 50 && !analyzedNums.has(c.chapter_number)
  )
})

// 解析钩子数据
function parseHooks(data: any): Array<{ type: string; content: string }> {
  if (!data) return []
  if (Array.isArray(data)) return data.map(h => ({ type: h.type || '', content: typeof h === 'string' ? h : (h.description || h.content || JSON.stringify(h)) }))
  if (typeof data === 'object') {
    const arr = data.hooks || data.items || []
    return arr.map((h: any) => ({ type: h.type || '', content: typeof h === 'string' ? h : (h.description || h.content || JSON.stringify(h)) }))
  }
  return []
}

// 解析建议
function parseSuggestions(data: any): string[] {
  if (!Array.isArray(data)) return []
  return data.map(s => typeof s === 'string' ? s : (s.suggestion || s.content || JSON.stringify(s)))
}

// 解析情节点（兼容字符串和 {event, quote} 对象）
function parseKeyPoints(data: any): Array<{ event: string; quote?: string }> {
  if (!Array.isArray(data)) return []
  return data.map(p => {
    if (typeof p === 'string') return { event: p }
    if (typeof p === 'object' && p) {
      return { event: p.event || p.description || p.quote || '', quote: p.quote || '' }
    }
    return { event: '' }
  }).filter(p => p.event)
}

// 解析冲突
function parseConflicts(data: any): Array<{ type: string; description: string }> {
  if (!Array.isArray(data)) return []
  return data.map(c => ({
    type: c.type || '',
    description: typeof c === 'string' ? c : (c.description || JSON.stringify(c)),
  }))
}

// 解析角色状态
function parseCharacterStates(data: any[]): Array<{ name: string; state: string; survival: string }> {
  if (!Array.isArray(data)) return []
  return data.map(cs => ({
    name: typeof cs === 'object' ? (cs.character || cs.character_name || '角色') : '角色',
    state: typeof cs === 'object' ? (cs.state_after || cs.mental_change || cs.change || '') : cs,
    survival: typeof cs === 'object' ? (cs.survival_status || '') : '',
  }))
}

// 计算各 tab 的数据计数
const hookCount = computed(() => parseHooks(detail.value?.hooks).length)
const foreshadowCount = computed(() => (detail.value?.foreshadows || []).length)
const conflictCount = computed(() => parseConflicts(detail.value?.conflicts).length)
const characterCount = computed(() => parseCharacterStates(detail.value?.character_states).length)
const suggestionCount = computed(() => parseSuggestions(detail.value?.suggestions).length)
</script>

<template>
  <div class="analysis-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="page-header-left">
        <h1 class="page-title">📊 剧情分析</h1>
        <p class="page-desc">AI 多维度分析章节质量，发现改进空间</p>
      </div>
      <div class="page-header-right">
        <a-button
          type="primary"
          :loading="analyzingAll"
          :disabled="!unanalyzedChapters.length"
          @click="analyzeAll"
        >
          🤖 一键分析未分析章节（{{ unanalyzedChapters.length }}）
        </a-button>
      </div>
    </div>

    <div class="analysis-body">
      <!-- 左侧章节列表 -->
      <div class="chapter-sidebar">
        <div class="sidebar-title">章节列表</div>
        <div class="chapter-list">
          <div
            v-for="c in (chapters||[])"
            :key="c.id"
            class="chapter-item"
            :class="{ active: selectedChapter === c.chapter_number }"
            @click="viewDetail(c.chapter_number)"
          >
            <div class="chapter-item-left">
              <span class="chapter-num">{{ c.chapter_number }}</span>
              <span class="chapter-label">第{{ c.chapter_number }}章</span>
            </div>
            <div class="chapter-item-right">
              <a-tag v-if="c.quality_alert && c.quality_alert.includes('consistency_issue')" color="red" size="small">⚠矛盾</a-tag>
              <a-tag v-if="c.quality_alert && c.quality_alert.includes('low_score')" color="orange" size="small">低分</a-tag>
              <span v-if="analysisMap[c.chapter_number]" class="status-dot success" />
              <span v-else-if="c.content && c.content.length > 50" class="status-dot pending" />
              <span v-else class="status-dot empty" />
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧分析内容 -->
      <div class="analysis-content">
        <!-- 加载中 -->
        <div v-if="loading" class="state-wrap">
          <a-spin size="large" />
          <div class="state-text">加载分析数据...</div>
        </div>

        <!-- 未选择章节 -->
        <div v-else-if="!selectedChapter" class="state-wrap">
          <div class="state-icon">📊</div>
          <div class="state-text">从左侧选择一个章节查看分析</div>
        </div>

        <!-- 无分析数据 -->
        <div v-else-if="!detail || !detail.id || detail.detail" class="state-wrap">
          <div class="state-icon">📭</div>
          <div class="state-text">{{ detail?.detail || '该章节暂无分析数据' }}</div>
          <a-button type="primary" :loading="analyzing" @click="analyzeChapter(chapterIdByNumber(selectedChapter)!, selectedChapter)">
            {{ analyzing ? '提交中...' : '🤖 开始分析此章节' }}
          </a-button>
        </div>

        <!-- 分析结果 -->
        <template v-else>
          <!-- 工具栏 -->
          <div class="content-toolbar">
            <div class="toolbar-title">第{{ detail.chapter_number }}章 · 剧情分析</div>
            <div class="toolbar-actions">
              <!-- 视图切换 -->
              <a-radio-group v-model:value="viewMode" size="small" button-style="solid">
                <a-radio-button value="annotation">📖 正文标注</a-radio-button>
                <a-radio-button value="report">📊 详细报告</a-radio-button>
              </a-radio-group>
              <a-button size="small" :disabled="!navInfo.hasPrev" @click="goPrevChapter">← 上一章</a-button>
              <a-button size="small" :disabled="!navInfo.hasNext" @click="goNextChapter">下一章 →</a-button>
              <a-button size="small" :loading="analyzing" @click="analyzeChapter(chapterIdByNumber(detail.chapter_number)!, detail.chapter_number)">
                🔄 {{ analyzing ? '提交中...' : '重新分析' }}
              </a-button>
            </div>
          </div>

          <!-- ===== 视图：正文 + 标注（对标 MuMu ChapterAnalysis 三栏联动）===== -->
          <div v-if="viewMode === 'annotation'" class="annotation-view">
            <div class="annot-main">
              <!-- 标注开关 -->
              <div v-if="annotationSummary.total" class="annot-toolbar">
                <a-switch v-model:checked="showAnnotations" size="small" />
                <span class="annot-switch-label">显示标注</span>
                <span class="annot-summary">
                  共 {{ annotationSummary.total }} 个
                  <span v-for="g in annotationGroups" :key="g.type" :style="{ color: g.color }">
                    {{ g.icon }} {{ g.items.length }}
                  </span>
                </span>
                <a-tooltip v-if="unlocatedCount" :title="`${unlocatedCount} 个标注未在正文精确定位，仅在右侧列表显示`">
                  <span class="annot-unlocated">{{ unlocatedCount }} 个未定位</span>
                </a-tooltip>
              </div>
              <div v-if="annotationSummary.has_analysis === false" class="annot-hint">
                该章节尚未分析，暂无标注。可点击「重新分析」生成。
              </div>
              <ClientOnly>
                <div class="annot-content">
                  <AnnotatedText
                    v-if="chapterContent && showAnnotations && locatedAnnotations.length"
                    :content="chapterContent"
                    :annotations="locatedAnnotations"
                    :active-id="activeAnnotation ? `${activeAnnotation.type}-${activeAnnotation.position}` : null"
                    @select="(a: any) => activeAnnotation = a"
                  />
                  <div v-else-if="chapterContent" class="annot-raw">{{ chapterContent }}</div>
                  <a-empty v-else description="暂无章节内容" />
                </div>
              </ClientOnly>
            </div>
            <!-- 标注侧边栏 -->
            <div class="annot-side">
              <div class="annot-side-title">
                <span>本章标注</span>
                <span v-if="annotationSummary.total" class="annot-side-count">{{ annotationSummary.total }}</span>
              </div>
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
                  @click="activeAnnotation = a"
                >
                  <div class="annot-item-title">{{ a.title || '—' }}</div>
                  <div class="annot-item-content">{{ a.content || '' }}</div>
                </div>
              </div>
            </div>
          </div>

          <!-- ===== 视图：详细报告（原有 Tabs）===== -->
          <div v-else class="report-view">

          <!-- 概览信息条 -->
          <div class="overview-bar">
            <div class="overview-item" v-if="detail.plot_stage">
              <span class="overview-label">剧情阶段</span>
              <a-tag color="blue">{{ detail.plot_stage }}</a-tag>
            </div>
            <div class="overview-item" v-if="detail.pacing">
              <span class="overview-label">节奏</span>
              <a-tag color="cyan">{{ pacingText(detail.pacing) }}</a-tag>
            </div>
            <div class="overview-item" v-if="detail.dialogue_ratio">
              <span class="overview-label">对话占比</span>
              <span class="overview-value">{{ (detail.dialogue_ratio * 100).toFixed(0) }}%</span>
            </div>
            <div class="overview-item" v-if="detail.description_ratio">
              <span class="overview-label">描写占比</span>
              <span class="overview-value">{{ (detail.description_ratio * 100).toFixed(0) }}%</span>
            </div>
            <div class="overview-item" v-if="detail.conflict_types?.length">
              <span class="overview-label">冲突类型</span>
              <a-tag v-for="ct in detail.conflict_types" :key="ct" color="red">{{ ct }}</a-tag>
            </div>
          </div>

          <!-- Tab 内容 -->
          <a-tabs v-model:activeKey="activeTab" size="small" class="analysis-tabs">
            <!-- Tab 1: 总览 -->
            <a-tab-pane key="overview" tab="📋 总览">
              <div class="tab-scroll">
                <!-- 评分卡片（分组布局：整体质量大卡 / 核心三维 / 番茄三维 / 其他） -->
                <div v-if="allScoreCards.length" class="score-section">
                  <!-- 整体质量（大卡，跨满） -->
                  <div v-if="overallCard" class="score-card overall" :style="{ '--c': scoreColor(overallCard.value) }">
                    <div class="score-label">整体质量</div>
                    <div class="score-num-big" :style="{ color: scoreColor(overallCard.value) }">
                      {{ overallCard.value.toFixed(1) }}<span class="score-unit">/10</span>
                    </div>
                    <div class="score-bar overall-bar">
                      <div class="score-bar-fill" :style="{ width: (overallCard.value * 10) + '%', backgroundColor: scoreColor(overallCard.value) }" />
                    </div>
                    <div class="score-level" :style="{ color: scoreColor(overallCard.value) }">{{ scoreLevel(overallCard.value) }}</div>
                  </div>
                  <!-- 核心三维：节奏 / 吸引力 / 连贯性 -->
                  <div v-if="coreCards.length" class="score-row">
                    <div v-for="s in coreCards" :key="s.key" class="score-card mini">
                      <div class="score-label">{{ s.label }}</div>
                      <div class="score-num" :style="{ color: scoreColor(s.value) }">{{ s.value.toFixed(1) }}</div>
                      <div class="score-bar">
                        <div class="score-bar-fill" :style="{ width: (s.value * 10) + '%', backgroundColor: scoreColor(s.value) }" />
                      </div>
                    </div>
                  </div>
                  <!-- 番茄三维：吸量力 / 留存力 / 追更比潜力 -->
                  <div v-if="tomatoCards.length" class="score-row">
                    <div v-for="s in tomatoCards" :key="s.key" class="score-card mini tomato">
                      <div class="score-label">{{ s.label }}</div>
                      <div class="score-num" :style="{ color: scoreColor(s.value) }">{{ s.value.toFixed(1) }}</div>
                      <div class="score-bar">
                        <div class="score-bar-fill" :style="{ width: (s.value * 10) + '%', backgroundColor: scoreColor(s.value) }" />
                      </div>
                    </div>
                  </div>
                  <!-- 其他维度（文笔/角色/对话/设定/逻辑） -->
                  <div v-if="otherCards.length" class="score-row others">
                    <div v-for="s in otherCards" :key="s.key" class="score-card mini">
                      <div class="score-label">{{ s.label }}</div>
                      <div class="score-num" :style="{ color: scoreColor(s.value) }">{{ s.value.toFixed(1) }}</div>
                      <div class="score-bar">
                        <div class="score-bar-fill" :style="{ width: (s.value * 10) + '%', backgroundColor: scoreColor(s.value) }" />
                      </div>
                    </div>
                  </div>
                </div>

                <!-- 评分理由 -->
                <div v-if="scoreJustification" class="section-card justify">
                  <div class="section-card-title">📝 评分理由</div>
                  <div class="justify-text">{{ scoreJustification }}</div>
                </div>

                <!-- 分析摘要（完整报告文本） -->
                <div v-if="detail.analysis_report" class="section-card">
                  <div class="section-card-title">📄 分析摘要</div>
                  <pre class="report-pre">{{ detail.analysis_report }}</pre>
                </div>

                <!-- 一致性问题 -->
                <div v-if="detail.consistency_issues?.length" class="section-card warn">
                  <div class="section-card-title">⚠️ 一致性问题</div>
                  <div v-for="(issue, i) in detail.consistency_issues" :key="i" class="issue-item">
                    {{ typeof issue === 'string' ? issue : JSON.stringify(issue) }}
                  </div>
                </div>

                <!-- 改进建议 -->
                <div v-if="parseSuggestions(detail.suggestions).length" class="section-card">
                  <div class="section-card-title">💡 改进建议</div>
                  <div v-for="(s, i) in parseSuggestions(detail.suggestions)" :key="i" class="suggestion-item">
                    <span class="suggestion-badge">{{ i + 1 }}</span>
                    <span>{{ s }}</span>
                  </div>
                </div>
              </div>
            </a-tab-pane>

            <!-- Tab 2: 钩子 -->
            <a-tab-pane key="hooks">
              <template #tab>🎣 钩子 <a-badge v-if="hookCount" :count="hookCount" :number-style="{ backgroundColor: '#C75B5B', fontSize: '11px' }" /></template>
              <div class="tab-scroll">
                <div v-if="hookCount" class="data-list">
                  <div v-for="(h, i) in parseHooks(detail.hooks)" :key="i" class="data-card">
                    <a-tag v-if="h.type" color="blue">{{ h.type }}</a-tag>
                    <div class="data-text">{{ h.content }}</div>
                  </div>
                </div>
                <a-empty v-else description="暂无钩子数据" />
              </div>
            </a-tab-pane>

            <!-- Tab 3: 伏笔 -->
            <a-tab-pane key="foreshadows">
              <template #tab>🔮 伏笔 <a-badge v-if="foreshadowCount" :count="foreshadowCount" :number-style="{ backgroundColor: '#1677FF', fontSize: '11px' }" /></template>
              <div class="tab-scroll">
                <div v-if="foreshadowCount" class="data-list">
                  <div v-for="(f, i) in detail.foreshadows" :key="i" class="data-card">
                    <div class="data-card-top">
                      <a-tag size="small">{{ typeof f === 'object' ? (f.action || f.type || '伏笔') : '伏笔' }}</a-tag>
                    </div>
                    <div class="data-text">{{ typeof f === 'object' ? (f.title || f.description || JSON.stringify(f)) : f }}</div>
                  </div>
                </div>
                <a-empty v-else description="暂无伏笔数据" />
              </div>
            </a-tab-pane>

            <!-- Tab 4: 冲突与情节点 -->
            <a-tab-pane key="conflicts">
              <template #tab>⚡ 冲突 <a-badge v-if="conflictCount" :count="conflictCount" :number-style="{ backgroundColor: '#D49A4E', fontSize: '11px' }" /></template>
              <div class="tab-scroll">
                <!-- 关键情节点 -->
                <div v-if="parseKeyPoints(detail.key_plot_points).length" class="section-card">
                  <div class="section-card-title">⭐ 关键情节点</div>
                  <div v-for="(p, i) in parseKeyPoints(detail.key_plot_points)" :key="i" class="data-card">
                    <div class="data-card-top">
                      <span class="item-no">{{ i + 1 }}</span>
                    </div>
                    <div class="data-text">{{ p.event }}</div>
                    <div v-if="p.quote" class="data-quote">「{{ p.quote }}」</div>
                  </div>
                </div>
                <!-- 冲突 -->
                <div v-if="conflictCount" class="data-list">
                  <div v-for="(c, i) in parseConflicts(detail.conflicts)" :key="i" class="data-card">
                    <div class="data-card-top">
                      <a-tag v-if="c.type" color="red">{{ c.type }}</a-tag>
                    </div>
                    <div class="data-text">{{ c.description }}</div>
                  </div>
                </div>
                <a-empty v-if="!parseKeyPoints(detail.key_plot_points).length && !conflictCount" description="暂无冲突数据" />
              </div>
            </a-tab-pane>

            <!-- Tab 5: 角色 -->
            <a-tab-pane key="characters">
              <template #tab>👤 角色 <a-badge v-if="characterCount" :count="characterCount" :number-style="{ backgroundColor: '#D49A4E', fontSize: '11px' }" /></template>
              <div class="tab-scroll">
                <div v-if="characterCount" class="data-list">
                  <div v-for="(cs, i) in parseCharacterStates(detail.character_states)" :key="i" class="data-card">
                    <div class="data-card-top">
                      <span class="data-title">{{ cs.name }}</span>
                      <a-tag v-if="cs.survival && cs.survival !== '存活'" color="red" size="small">{{ cs.survival }}</a-tag>
                    </div>
                    <div class="data-text">{{ cs.state }}</div>
                  </div>
                </div>
                <a-empty v-else description="暂无角色状态数据" />
              </div>
            </a-tab-pane>

            <!-- Tab 6: 情感 -->
            <a-tab-pane key="emotion" tab="🎭 情感">
              <div class="tab-scroll">
                <div v-if="detail.emotional_curve && Object.keys(detail.emotional_curve).length">
                  <div class="emotion-arc">
                    <div class="emotion-stage">
                      <div class="emotion-label">开头</div>
                      <div class="emotion-text">{{ detail.emotional_curve.start || '—' }}</div>
                    </div>
                    <div class="emotion-arrow">→</div>
                    <div class="emotion-stage">
                      <div class="emotion-label">中段</div>
                      <div class="emotion-text">{{ detail.emotional_curve.middle || '—' }}</div>
                    </div>
                    <div class="emotion-arrow">→</div>
                    <div class="emotion-stage">
                      <div class="emotion-label">结尾</div>
                      <div class="emotion-text">{{ detail.emotional_curve.end || '—' }}</div>
                    </div>
                  </div>
                  <div v-if="detail.emotional_curve.arc_summary" class="section-card">
                    <div class="section-card-title">情感弧线总结</div>
                    <div class="data-text">{{ detail.emotional_curve.arc_summary }}</div>
                  </div>
                </div>
                <a-empty v-else description="暂无情感数据" />
              </div>
            </a-tab-pane>

            <!-- Tab 7: 组织状态 -->
            <a-tab-pane v-if="detail.organization_states?.length" key="orgs">
              <template #tab>🏛️ 组织</template>
              <div class="tab-scroll">
                <div class="data-list">
                  <div v-for="(os, i) in detail.organization_states" :key="i" class="data-card">
                    <div class="data-card-top">
                      <a-tag color="purple" size="small">{{ typeof os === 'object' ? (os.organization || '组织') : '' }}</a-tag>
                    </div>
                    <div class="data-text">{{ typeof os === 'object' ? (os.change || JSON.stringify(os)) : os }}</div>
                  </div>
                </div>
              </div>
            </a-tab-pane>
          </a-tabs>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.analysis-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

/* 页面标题 */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 0;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--color-border);
}
.page-header-left { display: flex; align-items: baseline; gap: 12px; }
.page-title { margin: 0; font-size: 22px; font-weight: 700; color: var(--color-fg); }
.page-desc { margin: 0; font-size: 13px; color: var(--color-fg-muted); }

/* 主体布局 */
.analysis-body {
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
  overflow: hidden;
}

/* 左侧章节列表 */
.chapter-sidebar {
  width: 240px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg);
  overflow: hidden;
}
.sidebar-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-fg);
  padding: 12px 14px;
  border-bottom: 1px solid var(--color-border-light);
  background: var(--color-bg-page);
}
.chapter-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px;
}
.chapter-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all .15s;
  font-size: 13px;
  color: var(--color-fg-secondary);
}
.chapter-item:hover {
  background: var(--color-bg-page);
}
.chapter-item.active {
  background: var(--color-info-bg);
  color: var(--color-primary);
  font-weight: 600;
}
.chapter-item-left { display: flex; align-items: center; gap: 8px; }
.chapter-num {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--color-bg-page);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-fg-muted);
  flex-shrink: 0;
}
.chapter-item.active .chapter-num {
  background: var(--color-primary);
  color: #fff;
}
.chapter-label { white-space: nowrap; }
.chapter-item-right { display: flex; align-items: center; gap: 4px; }
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.status-dot.success { background: var(--color-success); }
.status-dot.pending { background: var(--color-warning); }
.status-dot.empty { background: var(--color-border); }

/* 右侧内容区 */
.analysis-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg);
  overflow: hidden;
  min-width: 0;
}

/* 状态页 */
.state-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  gap: 12px;
}
.state-icon { font-size: 48px; }
.state-text { color: var(--color-fg-muted); font-size: 14px; }

/* 工具栏 */
.content-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid var(--color-border-light);
  background: var(--color-bg-page);
}
.toolbar-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-fg);
}
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* 概览信息条 */
.overview-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--color-border-light);
}
.overview-item { display: flex; align-items: center; gap: 4px; }
.overview-label { font-size: 13px; color: var(--color-fg-muted); }
.overview-value { font-size: 13px; color: var(--color-fg-secondary); font-weight: 500; }

/* Tabs */
.analysis-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.analysis-tabs :deep(.ant-tabs-nav) {
  padding: 0 16px;
  margin-bottom: 0;
}
.analysis-tabs :deep(.ant-tabs-content) {
  flex: 1;
  min-height: 0;
}
.analysis-tabs :deep(.ant-tabs-tabpane) {
  height: 100%;
}
.tab-scroll {
  height: calc(100vh - 340px);
  min-height: 300px;
  overflow-y: auto;
  padding: 16px;
}

/* 评分 */
.score-section { margin-bottom: 20px; display: flex; flex-direction: column; gap: 10px; }

/* 整体质量大卡（跨满，突出显示） */
.score-card.overall {
  background: linear-gradient(135deg, #F0F5F5, #EAF0F1);
  border: 1px solid var(--color-info-border);
  border-radius: var(--radius-lg);
  padding: 16px 24px;
  display: flex;
  align-items: center;
  gap: 20px;
}
.score-card.overall .score-label { font-size: 14px; font-weight: 600; color: var(--color-fg); margin: 0; flex-shrink: 0; }
.score-card.overall .score-num-big {
  font-size: 40px;
  font-weight: 700;
  line-height: 1;
  font-family: Georgia, serif;
  flex-shrink: 0;
}
.score-card.overall .score-unit { font-size: 16px; color: var(--color-fg-muted); font-weight: 500; }
.score-card.overall .overall-bar { flex: 1; height: 8px; margin: 0; border-radius: 4px; }
.score-card.overall .score-level { font-size: 13px; font-weight: 600; margin: 0; flex-shrink: 0; min-width: 36px; text-align: center; }

/* 评分行（三等分） */
.score-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}
.score-row.others { grid-template-columns: repeat(auto-fit, minmax(80px, 1fr)); }
.score-card.mini {
  background: var(--color-bg-page);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  text-align: center;
}
.score-card.mini.tomato {
  background: linear-gradient(135deg, #FFF7E6, #FFFBF0);
  border-color: #FFE0B2;
}
.score-label { font-size: 11px; color: var(--color-fg-muted); margin-bottom: 4px; }
.score-num { font-size: 22px; font-weight: 700; line-height: 1.2; font-family: Georgia, serif; }
.score-level { font-size: 11px; font-weight: 600; margin-top: 2px; }
.score-bar {
  height: 4px;
  background: var(--color-border-light);
  border-radius: 2px;
  margin-top: 6px;
  overflow: hidden;
}
.score-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width .4s ease;
}

/* 区块卡片 */
.section-card {
  background: var(--color-bg-page);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 14px 16px;
  margin-bottom: 14px;
}
.section-card.warn {
  background: var(--color-danger-bg);
  border-color: #F0D0D0;
}
.section-card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-primary-dark);
  margin-bottom: 10px;
}

/* 建议 */
.suggestion-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  font-size: 14px;
  color: var(--color-fg-secondary);
  line-height: 1.6;
  padding: 4px 0;
}
.suggestion-badge {
  background: var(--color-primary);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
}

/* 问题 */
.issue-item {
  font-size: 14px;
  color: var(--color-danger);
  line-height: 1.6;
  padding: 6px 0;
  border-bottom: 1px solid #F0D0D0;
}
.issue-item:last-child { border-bottom: none; }

/* 评分理由 */
.section-card.justify { background: #EAF3F1; border-color: #C8DDD9; }
.justify-text {
  font-size: 13px;
  color: var(--color-fg-secondary);
  line-height: 1.8;
  white-space: pre-wrap;
}

/* 分析摘要报告 */
.report-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.8;
  color: var(--color-fg-secondary);
}

/* 数据卡片 */
.data-list { display: flex; flex-direction: column; gap: 8px; }
.data-card {
  background: var(--color-bg-page);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 12px 14px;
}
.data-card-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}
.data-title { font-size: 14px; font-weight: 600; color: var(--color-fg); }
.data-text { font-size: 14px; color: var(--color-fg-secondary); line-height: 1.6; }
.data-quote {
  font-size: 12px;
  color: var(--color-fg-muted);
  line-height: 1.6;
  margin-top: 4px;
  padding: 4px 8px;
  background: var(--color-bg-page);
  border-left: 2px solid var(--color-border);
  border-radius: 0 4px 4px 0;
  font-style: italic;
}
.item-no {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--color-primary);
  color: #fff;
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

/* 情感弧线 */
.emotion-arc {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}
.emotion-stage {
  flex: 1;
  text-align: center;
  padding: 12px;
  background: var(--color-bg-page);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}
.emotion-label { font-size: 11px; color: var(--color-fg-muted); margin-bottom: 4px; }
.emotion-text { font-size: 13px; color: var(--color-fg); }
.emotion-arrow { color: var(--color-info-border); font-size: 16px; }

/* ===== 视图切换容器 ===== */
.annotation-view, .report-view {
  flex: 1;
  display: flex;
  gap: 12px;
  min-height: 0;
  overflow: hidden;
}
.report-view { flex-direction: column; }
.report-view .overview-bar, .report-view .analysis-tabs { width: 100%; }

/* ===== 正文 + 标注三栏 ===== */
.annot-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg);
}
.annot-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--color-border-light);
  background: var(--color-bg-page);
  font-size: 13px;
}
.annot-switch-label { font-size: 13px; color: var(--color-fg-secondary); }
.annot-summary { font-size: 12px; color: var(--color-fg-muted); display: flex; gap: 10px; font-weight: 600; }
.annot-unlocated { font-size: 11px; color: var(--color-warning); padding: 1px 6px; background: var(--color-warning-bg); border-radius: 8px; }
.annot-hint { padding: 12px 16px; font-size: 13px; color: var(--color-warning); }
.annot-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px 28px;
  font-size: 15px;
  line-height: 2;
}
.annot-raw { white-space: pre-wrap; word-break: break-word; }

/* 标注侧边栏 */
.annot-side {
  width: 280px;
  flex-shrink: 0;
  overflow-y: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg);
  padding: 10px;
}
.annot-side-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-primary-dark);
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--color-border-light);
}
.annot-side-count {
  background: var(--color-primary);
  color: #fff;
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 10px;
}
.annot-empty { font-size: 13px; color: var(--color-fg-muted); text-align: center; padding: 24px 0; }
.annot-group { margin-bottom: 12px; }
.annot-group-title { font-size: 12px; font-weight: 600; margin-bottom: 6px; }
.annot-item {
  padding: 8px 10px;
  background: var(--color-bg-page);
  border-radius: var(--radius-md);
  border-left: 3px solid var(--color-border);
  margin-bottom: 6px;
  cursor: pointer;
  transition: all .15s;
}
.annot-item:hover { background: var(--color-info-bg); }
.annot-item.active { background: var(--color-info-bg); border-left-width: 4px; }
.annot-item-title { font-size: 12px; font-weight: 600; color: var(--color-fg); margin-bottom: 3px; }
.annot-item-content {
  font-size: 12px;
  color: var(--color-fg-secondary);
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}
</style>
