<script setup lang="ts">
// 章节分析结果查看面板（对标 MuMuAINovel ChapterAnalysis）
import { apiGet } from '~/composables/useApi'

const props = defineProps<{
  chapterId: number
  chapterNumber: number
  qualityScore?: number | null
}>()

const emit = defineEmits<{ (e: 'close'): void }>()

const { currentProjectId } = useProject()
const msg = useMessage()

const visible = ref(false)
const loading = ref(false)
const analysis = ref<any>(null)
const activeTab = ref('overview')

// 从章节模型获取的评分
const chapterScores = computed(() => {
  if (!analysis.value?.quality_scores) return null
  return analysis.value.quality_scores
})

// 质量标签
function scoreColor(score: number): string {
  if (score >= 8) return '#52A569'
  if (score >= 6) return '#4D8088'
  if (score >= 4) return '#D49A4E'
  return '#C75B5B'
}

// 打开面板
async function open() {
  visible.value = true
  loading.value = true
  analysis.value = null
  activeTab.value = 'overview'
  try {
    const data = await apiGet<any>(`/api/projects/${currentProjectId.value}/analyses/${props.chapterNumber}`).catch(() => null)
    if (data && !data.detail) {
      analysis.value = data
    }
  } catch (e: any) {
    msg.error('加载分析失败：' + formatError(e))
  } finally {
    loading.value = false
  }
}

// 触发分析
const analyzing = ref(false)
async function onAnalyze() {
  analyzing.value = true
  try {
    const api = useProjectApi()
    await api.triggerAnalysis(props.chapterId)
    msg.success('分析完成')
    // 重新加载
    const data = await apiGet<any>(`/api/projects/${currentProjectId.value}/analyses/${props.chapterNumber}`).catch(() => null)
    if (data && !data.detail) analysis.value = data
  } catch (e: any) {
    const status = e?.response?.status || e?.status
    if (status === 400) {
      msg.error('章节内容过少，无法分析')
    } else {
      msg.error('分析失败：' + formatError(e))
    }
  } finally {
    analyzing.value = false
  }
}

defineExpose({ open })
</script>

<template>
  <a-modal
    v-model:open="visible"
    :title="`📊 第${chapterNumber}章 分析报告`"
    width="800px"
    :footer="null"
    @cancel="emit('close')"
  >
    <!-- 加载中 -->
    <div v-if="loading" style="text-align: center; padding: 40px">
      <a-spin size="large" />
      <div style="margin-top: 12px; color: #8C8C8C">加载分析数据...</div>
    </div>

    <!-- 无分析数据 -->
    <div v-else-if="!analysis" style="text-align: center; padding: 40px">
      <div style="font-size: 48px; margin-bottom: 16px">📊</div>
      <div style="color: #8C8C8C; margin-bottom: 16px">该章节尚未进行剧情分析</div>
      <a-button type="primary" :loading="analyzing" @click="onAnalyze">
        {{ analyzing ? '分析中...' : '开始分析' }}
      </a-button>
    </div>

    <!-- 分析结果 -->
    <template v-else>
      <a-tabs v-model:activeKey="activeTab">
        <!-- Tab 1: 总览 -->
        <a-tab-pane key="overview" tab="总览">
          <!-- 质量评分 -->
          <div v-if="chapterScores" class="scores-grid">
            <div v-for="(val, key) in chapterScores" :key="key" class="score-item">
              <div class="score-label">{{ key }}</div>
              <div class="score-value" :style="{ color: scoreColor(val) }">{{ val }}/10</div>
            </div>
          </div>
          <div v-else-if="qualityScore" class="scores-grid">
            <div class="score-item">
              <div class="score-label">综合评分</div>
              <div class="score-value" :style="{ color: scoreColor(qualityScore) }">{{ qualityScore }}/10</div>
            </div>
          </div>

          <!-- 剧情阶段 -->
          <div v-if="analysis.plot_stage" class="info-row">
            <span class="info-label">剧情阶段：</span>
            <a-tag color="blue">{{ analysis.plot_stage }}</a-tag>
            <span v-if="analysis.pacing" class="info-label" style="margin-left: 16px">节奏：</span>
            <a-tag v-if="analysis.pacing" color="cyan">{{ analysis.pacing }}</a-tag>
          </div>

          <!-- 对话/描写比例 -->
          <div v-if="analysis.dialogue_ratio || analysis.description_ratio" class="info-row">
            <span class="info-label">对话比例：</span>
            <span>{{ ((analysis.dialogue_ratio || 0) * 100).toFixed(0) }}%</span>
            <span class="info-label" style="margin-left: 16px">描写比例：</span>
            <span>{{ ((analysis.description_ratio || 0) * 100).toFixed(0) }}%</span>
          </div>

          <!-- 建议 -->
          <div v-if="analysis.suggestions?.length" class="section">
            <div class="section-title">💡 改进建议</div>
            <div v-for="(s, i) in analysis.suggestions" :key="i" class="suggestion-item">
              <span class="suggestion-num">{{ i + 1 }}.</span>
              <span>{{ typeof s === 'string' ? s : s.content || s.text || JSON.stringify(s) }}</span>
            </div>
          </div>
        </a-tab-pane>

        <!-- Tab 2: 钩子 -->
        <a-tab-pane key="hooks">
          <template #tab>🎣 钩子 <a-badge :count="analysis.hooks?.length || 0" :number-style="{ backgroundColor: '#C75B5B' }" /></template>
          <div v-if="analysis.hooks?.length" class="item-list">
            <div v-for="(h, i) in analysis.hooks" :key="i" class="list-card">
              <div class="list-card-head">
                <a-tag v-if="h.type" color="blue">{{ h.type }}</a-tag>
                <a-tag v-if="h.position" color="orange">{{ h.position }}</a-tag>
                <a-tag v-if="h.strength" color="red">强度: {{ h.strength }}/10</a-tag>
              </div>
              <div class="list-card-body">{{ h.content || h.text || '' }}</div>
            </div>
          </div>
          <a-empty v-else description="暂无钩子" />
        </a-tab-pane>

        <!-- Tab 3: 伏笔 -->
        <a-tab-pane key="foreshadows">
          <template #tab>🔮 伏笔 <a-badge :count="analysis.foreshadows?.length || 0" :number-style="{ backgroundColor: '#1677FF' }" /></template>
          <div v-if="analysis.foreshadows?.length" class="item-list">
            <div v-for="(f, i) in analysis.foreshadows" :key="i" class="list-card">
              <div class="list-card-head">
                <a-tag :color="f.type === 'planted' ? 'green' : 'purple'">
                  {{ f.type === 'planted' ? '已埋下' : '已回收' }}
                </a-tag>
                <a-tag v-if="f.strength" color="orange">强度: {{ f.strength }}/10</a-tag>
                <a-tag v-if="f.subtlety" color="cyan">隐藏度: {{ f.subtlety }}/10</a-tag>
                <a-tag v-if="f.reference_chapter" color="blue">呼应第{{ f.reference_chapter }}章</a-tag>
              </div>
              <div class="list-card-body">{{ f.content || f.text || '' }}</div>
            </div>
          </div>
          <a-empty v-else description="暂无伏笔" />
        </a-tab-pane>

        <!-- Tab 4: 冲突 -->
        <a-tab-pane key="conflicts">
          <template #tab>⚡ 冲突 <a-badge :count="analysis.conflicts?.length || 0" :number-style="{ backgroundColor: '#D49A4E' }" /></template>
          <div v-if="analysis.conflict_types?.length" style="margin-bottom: 12px">
            <span class="info-label">冲突类型：</span>
            <a-tag v-for="t in analysis.conflict_types" :key="t" color="red" style="margin: 2px">{{ t }}</a-tag>
          </div>
          <div v-if="analysis.conflicts?.length" class="item-list">
            <div v-for="(c, i) in analysis.conflicts" :key="i" class="list-card">
              <div class="list-card-body">{{ typeof c === 'string' ? c : c.content || c.text || JSON.stringify(c) }}</div>
            </div>
          </div>
          <a-empty v-else description="暂无冲突" />
        </a-tab-pane>

        <!-- Tab 5: 角色 -->
        <a-tab-pane key="characters">
          <template #tab>👤 角色 <a-badge :count="analysis.character_states?.length || 0" :number-style="{ backgroundColor: '#D49A4E' }" /></template>
          <div v-if="analysis.character_states?.length" class="item-list">
            <div v-for="(cs, i) in analysis.character_states" :key="i" class="list-card">
              <div class="list-card-head">
                <strong>{{ cs.character_name || cs.name || '未知角色' }}</strong>
              </div>
              <div v-if="cs.state_before || cs.state_after" class="list-card-body">
                <span v-if="cs.state_before">{{ cs.state_before }}</span>
                <span v-if="cs.state_before && cs.state_after" style="color: #4D8088"> → </span>
                <span v-if="cs.state_after">{{ cs.state_after }}</span>
              </div>
              <div v-if="cs.key_event" class="list-card-body" style="color: #595959">
                关键事件：{{ cs.key_event }}
              </div>
              <div v-if="cs.psychological_change" class="list-card-body" style="color: #8C8C8C; font-size: 13px">
                心理变化：{{ cs.psychological_change }}
              </div>
            </div>
          </div>
          <a-empty v-else description="暂无角色状态" />
        </a-tab-pane>

        <!-- Tab 6: 情感 -->
        <a-tab-pane key="emotion" tab="🎭 情感">
          <div v-if="analysis.emotional_curve?.dominant_emotion" class="info-row">
            <span class="info-label">主导情感：</span>
            <a-tag color="blue">{{ analysis.emotional_curve.dominant_emotion }}</a-tag>
            <span class="info-label" style="margin-left: 16px">情感强度：</span>
            <span>{{ ((analysis.emotional_curve.emotional_intensity || 0) * 10).toFixed(0) }}/10</span>
          </div>
          <div v-if="analysis.emotion_curve?.length" class="emotion-list">
            <div v-for="(e, i) in analysis.emotion_curve" :key="i" class="emotion-item">
              <span class="emotion-label">{{ e.label || e.emotion || '' }}</span>
              <a-progress :percent="(e.value || e.intensity || 0) * 10" :stroke-color="scoreColor((e.value || e.intensity || 0) * 10)" size="small" />
            </div>
          </div>
          <a-empty v-if="!analysis.emotional_curve?.dominant_emotion && !analysis.emotion_curve?.length" description="暂无情感数据" />
        </a-tab-pane>
      </a-tabs>

      <!-- 底部操作 -->
      <div class="panel-footer">
        <a-button :loading="analyzing" @click="onAnalyze">
          {{ analyzing ? '分析中...' : '🔄 重新分析' }}
        </a-button>
      </div>
    </template>
  </a-modal>
</template>

<style scoped>
.scores-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.score-item {
  background: #FAFAF7;
  border: 1px solid #E8E4DC;
  border-radius: 8px;
  padding: 12px;
  text-align: center;
}
.score-label { font-size: 12px; color: #8C8C8C; margin-bottom: 4px; }
.score-value { font-size: 20px; font-weight: 700; }
.info-row { margin-bottom: 12px; font-size: 14px; display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.info-label { font-size: 13px; color: #8C8C8C; }
.section { margin-top: 16px; }
.section-title { font-size: 15px; font-weight: 600; color: #4D8088; margin-bottom: 8px; }
.suggestion-item { font-size: 14px; color: #595959; padding: 4px 0; display: flex; gap: 6px; }
.suggestion-num { color: #4D8088; font-weight: 600; min-width: 20px; }
.item-list { display: flex; flex-direction: column; gap: 10px; }
.list-card { background: #FAFAF7; border: 1px solid #E8E4DC; border-radius: 8px; padding: 12px; }
.list-card-head { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 6px; }
.list-card-body { font-size: 14px; color: #2B2B2B; line-height: 1.6; }
.emotion-list { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
.emotion-item { display: flex; align-items: center; gap: 10px; }
.emotion-label { font-size: 13px; color: #595959; min-width: 60px; }
.panel-footer { display: flex; justify-content: flex-end; margin-top: 16px; padding-top: 12px; border-top: 1px solid #E8E4DC; }
</style>
