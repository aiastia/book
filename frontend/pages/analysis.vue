<script setup lang="ts">
// 剧情分析：对标参考站 — 按章节展示分析维度（钩子/情节点/冲突/角色状态/评分/建议）
import { useProjectApi } from '~/composables/useProjectApi'
import { useProject } from '~/composables/useProject'
useHead({ title: '剧情分析 — 墨语' })
const { currentProjectId } = useProject()
if (!currentProjectId.value) await navigateTo('/books')
const api = useProjectApi()
const msg = useMessage()
const { data: analyses, refresh } = await api.getAnalyses()
const { data: chapters } = await api.getChapters()

// 选择章节查看详情
const selectedChapter = ref<number | null>(null)
const detail = ref<any>(null)
const loading = ref(false)

async function viewDetail(chapterNumber: number) {
  selectedChapter.value = chapterNumber
  loading.value = true
  detail.value = null
  try {
    const r = await api.getAnalysis(chapterNumber)
    detail.value = r
  } catch (e: any) {
    const status = e?.response?.status || e?.status
    if (status === 404) {
      detail.value = null  // 无分析数据，显示空状态
    } else {
      detail.value = { detail: '加载失败：' + formatError(e) }
    }
  } finally { loading.value = false }
}

const analysisMap = computed(() => {
  const m: Record<number, any> = {}
  for (const a of (analyses.value||[])) {
    // 只有当分析有实际数据（quality_scores 或 plot_stage）才算真正已分析
    if (a && (a.quality_scores || a.plot_stage)) {
      m[a.chapter_number] = a
    }
  }
  return m
})

// 评分维度中文映射
const scoreLabels: Record<string, string> = {
  pacing: '节奏',
  engagement: '吸引力',
  coherence: '连贯性',
  writing_quality: '文笔',
  character_depth: '角色',
  dialogue_quality: '对话',
  world_consistency: '设定',
  plot_logic: '逻辑',
  overall: '综合',
}

const scoreText = (qs: any) => {
  if (!qs || typeof qs !== 'object') return '-'
  return qs.overall || qs.pacing || '-'
}

// 手动触发分析（对标 MuMu）
const analyzing = ref(false)
const analyzingAll = ref(false)

async function analyzeChapter(chapterId: number, chapterNumber: number) {
  analyzing.value = true
  msg.info(`正在分析第${chapterNumber}章，请耐心等待…`)
  try {
    const r = await api.triggerAnalysis(chapterId)
    msg.success(`第${chapterNumber}章分析完成`)
    // 刷新分析列表 + 重新加载详情
    await refresh()
    await viewDetail(chapterNumber)
  } catch (e: any) {
    const status = e?.response?.status || e?.status
    if (status === 400) {
      msg.error('分析失败：章节内容过少，无法分析')
    } else {
      msg.error('分析失败：' + formatError(e))
    }
  } finally {
    analyzing.value = false
  }
}

async function analyzeAll() {
  if (!await msg.confirm('将分析所有未分析的章节，可能需要较长时间。确认开始？')) return
  analyzingAll.value = true
  msg.info('正在批量分析，请耐心等待…')
  try {
    const r = await api.analyzeAllUnanalyzed()
    await refresh()
    if (r.analyzed > 0) {
      msg.success(`分析完成：成功 ${r.analyzed} 章` + (r.failed.length ? `，失败 ${r.failed.length} 章` : ''))
    } else {
      msg.info('所有章节都已分析过')
    }
  } catch (e: any) {
    msg.error('批量分析失败：' + formatError(e))
  } finally {
    analyzingAll.value = false
  }
}

// 找章节ID（用于手动分析）
function chapterIdByNumber(num: number): number | null {
  const c = (chapters.value || []).find((x: any) => x.chapter_number === num)
  return c?.id || null
}

// 找未分析的章节（有内容但无分析）
const unanalyzedChapters = computed(() => {
  const analyzedNums = new Set((analyses.value || []).map((a: any) => a.chapter_number))
  return (chapters.value || []).filter((c: any) =>
    c.content && c.content.length > 50 && !analyzedNums.has(c.chapter_number)
  )
})
</script>

<template>
  <div class="analysis-page">
    <!-- 操作栏 -->
    <div class="analysis-actions">
      <a-button :loading="analyzingAll" :disabled="!unanalyzedChapters.length" @click="analyzeAll">
        🤖 一键分析未分析章节（{{ unanalyzedChapters.length }}）
      </a-button>
    </div>
    <!-- 章节列表（带分析状态） -->
    <div class="ch-selector">
      <div v-for="c in (chapters||[])" :key="c.id"
        class="ch-sel-item" :class="{active: selectedChapter===c.chapter_number}"
        @click="viewDetail(c.chapter_number)">
        <span>第{{ c.chapter_number }}章</span>
        <div style="display:flex;gap:4px;align-items:center;">
          <a-tag v-if="c.quality_alert && c.quality_alert.includes('consistency_issue')" color="red" size="small">⚠️矛盾</a-tag>
          <a-tag v-if="c.quality_alert && c.quality_alert.includes('low_score')" color="orange" size="small">低分</a-tag>
          <a-tag v-if="analysisMap[c.chapter_number]" color="success" size="small">已分析</a-tag>
          <a-tag v-else-if="c.content && c.content.length > 50" color="warning" size="small">未分析</a-tag>
          <a-tag v-else size="small">无内容</a-tag>
        </div>
      </div>
    </div>

    <!-- 分析详情 -->
    <div v-if="loading" style="text-align:center;padding:40px"><a-spin /></div>
    <!-- 未分析提示 + 分析按钮 -->
    <div v-if="!loading && (!detail || !detail.id || detail.detail)" class="detail-content">
      <a-empty :description="detail?.detail || '该章节暂无分析数据'" />
      <div v-if="selectedChapter" style="text-align:center;margin-top:16px">
        <a-button type="primary" :loading="analyzing"
          @click="analyzeChapter(chapterIdByNumber(selectedChapter)!, selectedChapter)">
          🤖 {{ analyzing ? '分析中…' : '立即分析此章节' }}
        </a-button>
      </div>
    </div>
    <div v-if="detail && detail.id && !detail.detail" class="detail-content">
      <!-- 重新分析按钮 -->
      <div class="detail-action-bar">
        <a-button size="small" :loading="analyzing"
          @click="analyzeChapter(chapterIdByNumber(detail.chapter_number)!, detail.chapter_number)">
          🔄 {{ analyzing ? '分析中…' : '重新分析' }}
        </a-button>
      </div>
      <!-- 剧情阶段 + 节奏 + 占比 -->
      <a-card size="small" style="margin-bottom:12px">
        <div class="meta-row">
          <a-tag v-if="detail.plot_stage" color="blue">阶段：{{ detail.plot_stage }}</a-tag>
          <a-tag v-if="detail.pacing" color="cyan">节奏：{{ {fast:'快',medium:'中',slow:'慢'}[detail.pacing] || detail.pacing }}</a-tag>
          <span v-if="detail.dialogue_ratio" class="ratio-pill">对话 {{ (detail.dialogue_ratio * 100).toFixed(0) }}%</span>
          <span v-if="detail.description_ratio" class="ratio-pill">描写 {{ (detail.description_ratio * 100).toFixed(0) }}%</span>
        </div>
      </a-card>
      <!-- 评分 -->
      <a-card v-if="detail.quality_scores" size="small" title="质量评分" style="margin-bottom:12px">
        <div class="score-grid">
          <div v-for="(v,k) in detail.quality_scores" :key="k" class="score-item" :class="{ 'score-low': v < 5, 'score-warn': v >= 5 && v < 7 }">
            <span class="score-label">{{ scoreLabels[k] || k }}</span>
            <span class="score-value">{{ v }}</span>
          </div>
        </div>
      </a-card>
      <!-- 一致性问题 -->
      <a-card v-if="detail.consistency_issues && detail.consistency_issues.length" size="small" title="⚠️ 一致性问题" style="margin-bottom:12px">
        <div v-for="(issue,i) in detail.consistency_issues" :key="i" class="analysis-item consistency-issue">
          <a-tag color="red" size="small">问题{{ i+1 }}</a-tag>
          {{ typeof issue === 'string' ? issue : JSON.stringify(issue) }}
        </div>
      </a-card>
      <!-- 情感曲线（#14） -->
      <a-card v-if="detail.emotional_curve && Object.keys(detail.emotional_curve).length" size="small" title="情感弧线" style="margin-bottom:12px">
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
        <div v-if="detail.emotional_curve.arc_summary" class="emotion-summary">{{ detail.emotional_curve.arc_summary }}</div>
      </a-card>
      <!-- 冲突类型（#14） -->
      <a-card v-if="detail.conflict_types && detail.conflict_types.length" size="small" style="margin-bottom:12px">
        <div class="conflict-types">
          <span class="ct-title">冲突类型：</span>
          <a-tag v-for="(ct,i) in detail.conflict_types" :key="i" color="volcano">{{ ct }}</a-tag>
        </div>
      </a-card>
      <!-- 钩子 -->
      <a-card v-if="detail.hooks && (Array.isArray(detail.hooks)?detail.hooks.length:Object.keys(detail.hooks).length)" size="small" title="钩子" style="margin-bottom:12px">
        <div v-for="(h,i) in (Array.isArray(detail.hooks)?detail.hooks:(detail.hooks.hooks||detail.hooks.items||[]))" :key="i" class="analysis-item">
          {{ typeof h==='string'?h:(h.description||h.content||JSON.stringify(h)) }}
        </div>
      </a-card>
      <!-- 关键情节点 -->
      <a-card v-if="detail.key_plot_points && detail.key_plot_points.length" size="small" title="关键情节点" style="margin-bottom:12px">
        <div v-for="(p,i) in detail.key_plot_points" :key="i" class="analysis-item">
          <span class="item-no">{{ i+1 }}</span>{{ typeof p==='string'?p:(p.event||p.description||JSON.stringify(p)) }}
        </div>
      </a-card>
      <!-- 冲突 -->
      <a-card v-if="detail.conflicts && detail.conflicts.length" size="small" title="冲突" style="margin-bottom:12px">
        <div v-for="(cf,i) in detail.conflicts" :key="i" class="analysis-item">
          <span class="item-no">{{ i+1 }}</span>{{ typeof cf==='string'?cf:(cf.description||cf.type||JSON.stringify(cf)) }}
        </div>
      </a-card>
      <!-- 组织状态变化（#14） -->
      <a-card v-if="detail.organization_states && detail.organization_states.length" size="small" title="组织状态变化" style="margin-bottom:12px">
        <div v-for="(os,i) in detail.organization_states" :key="i" class="analysis-item">
          <a-tag color="purple" size="small">{{ typeof os==='object'?(os.organization||'组织'):'' }}</a-tag>
          {{ typeof os==='object'?(os.change||JSON.stringify(os)):os }}
        </div>
      </a-card>
      <!-- 角色状态 -->
      <a-card v-if="detail.character_states && detail.character_states.length" size="small" title="角色状态变化" style="margin-bottom:12px">
        <div v-for="(cs,i) in detail.character_states" :key="i" class="analysis-item">
          <strong>{{ typeof cs==='object'?(cs.character||cs.character_name||'角色'):'' }}</strong>：
          {{ typeof cs==='object'?(cs.state_after||cs.mental_change||cs.change||'') : cs }}
          <a-tag v-if="typeof cs==='object' && cs.survival_status && cs.survival_status !== '存活'" size="small" color="red">{{ cs.survival_status }}</a-tag>
        </div>
      </a-card>
      <!-- 建议 -->
      <a-card v-if="detail.suggestions && detail.suggestions.length" size="small" title="改进建议" style="margin-bottom:12px">
        <div v-for="(s,i) in detail.suggestions" :key="i" class="analysis-item suggestion">💡 {{ typeof s==='string'?s:(s.suggestion||s.content||JSON.stringify(s)) }}</div>
      </a-card>
      <!-- 伏笔 -->
      <a-card v-if="detail.foreshadows && detail.foreshadows.length" size="small" title="伏笔动态" style="margin-bottom:12px">
        <div v-for="(f,i) in detail.foreshadows" :key="i" class="analysis-item">
          <a-tag size="small">{{ typeof f==='object'?(f.action||f.type||''):'伏笔' }}</a-tag>
          {{ typeof f==='object'?(f.title||f.description||JSON.stringify(f)):f }}
        </div>
      </a-card>
    </div>
    <a-empty v-else-if="selectedChapter" description="该章节暂无分析数据" />
    <a-empty v-else description="选择左侧章节查看分析详情" />
  </div>
</template>

<style scoped>
.analysis-page { display:grid; grid-template-columns:240px 1fr; gap:16px; min-height:400px; }
.ch-selector { display:flex; flex-direction:column; gap:6px; max-height:600px; overflow-y:auto; }
.ch-sel-item { display:flex; align-items:center; justify-content:space-between; padding:10px 12px; border:1px solid #E8E4DC; border-radius:8px; cursor:pointer; font-size:13px; transition:all .2s; }
.ch-sel-item:hover { border-color:#B8CDD1; }
.ch-sel-item.active { border-color:#4D8088; background:#EAF0F1; color:#4D8088; font-weight:600; }
.detail-content { }
.analysis-actions { grid-column: 1 / -1; margin-bottom: 8px; }
.detail-action-bar { display: flex; gap: 8px; margin-bottom: 12px; }
.score-grid { display:flex; flex-wrap:wrap; gap:12px; }
.score-item { display:flex; flex-direction:column; align-items:center; min-width:60px; }
.score-label { font-size:11px; color:#8C8C8C; }
.score-value { font-size:20px; font-weight:700; color:#4D8088; font-family:Georgia,serif; }
.analysis-item { padding:6px 0; font-size:14px; line-height:1.6; color:#595959; border-bottom:1px solid #F8F6F1; display:flex; gap:8px; }
.analysis-item:last-child { border-bottom:none; }
.item-no { width:20px; height:20px; border-radius:50%; background:#4D8088; color:#fff; font-size:11px; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.suggestion { color:#D49A4E; }
.meta-row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
.ratio-pill { font-size:12px; background:#F8F6F1; color:#595959; padding:2px 8px; border-radius:4px; }
.emotion-arc { display:flex; align-items:center; gap:8px; margin-bottom:8px; }
.emotion-stage { flex:1; text-align:center; padding:8px; background:#FAFAF7; border-radius:6px; }
.emotion-label { font-size:11px; color:#8C8C8C; margin-bottom:4px; }
.emotion-text { font-size:13px; color:#2B2B2B; }
.emotion-arrow { color:#B5C7CB; font-size:16px; }
.emotion-summary { font-size:13px; color:#595959; line-height:1.6; padding-top:8px; border-top:1px solid #F0EDE6; }
.conflict-types { display:flex; gap:6px; align-items:center; flex-wrap:wrap; }
.ct-title { font-size:13px; color:#595959; }
.score-low .score-value { color:#E74C3C; }
.score-warn .score-value { color:#D49A4E; }
.consistency-issue { color:#E74C3C; background:#FFF5F5; padding:8px; border-radius:6px; margin-bottom:4px; }
</style>
