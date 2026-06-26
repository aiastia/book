<script setup lang="ts">
// 批量生成面板（连续模式，对标 MuMuAINovel）：
// 选「起始章 + 数量(5/10/20/40) + 风格 + 字数 + 模型 + 视角」→ 提交 → 进度轮询 + 取消
import { useProjectApi } from '~/composables/useProjectApi'
import { useProject } from '~/composables/useProject'
import { useBackgroundTasks } from '~/composables/useBackgroundTasks'
import { apiGet } from '~/composables/useApi'

const props = defineProps<{
  chapters: any[]
}>()
const emit = defineEmits<{ (e: 'done'): void }>()

const api = useProjectApi()
const msg = useMessage()
const { trackTask } = useBackgroundTasks()
const { currentProjectId } = useProject()

const open = ref(false)
const submitting = ref(false)

// 表单
const startChapterNumber = ref<number>(1)
const count = ref(5)
const countOptions = [5, 10, 20, 40]
const targetWords = ref(4000)
const styleId = ref<number | null>(null)
const narrativePerspective = ref<string>('')  // 空 = 按小说设定
const aiModel = ref<string>('')               // 空 = 使用默认模型
const enableAnalysis = ref(true)

if (import.meta.client) {
  const s = localStorage.getItem('moyu_chapter_words')
  if (s) targetWords.value = Number(s)
}

// 写作风格列表 + 项目默认风格
const writingStyles = ref<any[]>([])
const remoteModels = ref<Array<{ id: string; owned_by: string }>>([])
const defaultModelName = ref('')
const loadingModels = ref(false)
const projectDefaultStyleName = ref('')

// 可选起始章（空章节，优先）
const emptyChapters = computed(() => {
  return (props.chapters || []).filter((c: any) => !c.content || c.content.trim().length < 100)
})
// 默认起始章 = 第一个空章节
const defaultStartChapter = computed(() => {
  if (emptyChapters.value.length) return emptyChapters.value[0].chapter_number
  const list = props.chapters || []
  return list.length ? list[list.length - 1].chapter_number + 1 : 1
})

// 从起始章开始，可用的空章节数量
const availableCount = computed(() => {
  const start = startChapterNumber.value || 1
  return emptyChapters.value.filter((c: any) => c.chapter_number >= start).length
})
// 实际生成数量 = 取用户选择和可用数的较小值
const actualCount = computed(() => {
  return Math.min(count.value, availableCount.value || 0)
})

// 项目默认叙事视角（用于 placeholder / 「按小说设定」展示）
const projectDefaultPov = ref('第三人称')

// 当前任务状态
const currentTask = ref<any>(null)
let pollTimer: any = null

function openPanel() {
  startChapterNumber.value = defaultStartChapter.value
  count.value = 5
  aiModel.value = ''
  narrativePerspective.value = ''
  loadWritingStyles()
  loadRemoteModels()
  loadProjectDefault()
  checkActiveTask()
  open.value = true
}

async function loadWritingStyles() {
  try {
    writingStyles.value = await apiGet<any[]>('/api/writing-styles') || []
  } catch {}
}

async function loadRemoteModels() {
  if (remoteModels.value.length) return
  loadingModels.value = true
  try {
    const r = await api.fetchDefaultRemoteModels()
    remoteModels.value = r.models || []
    defaultModelName.value = r.default_model || ''
  } catch (e: any) {
    console.warn('拉取模型列表失败', e)
  } finally {
    loadingModels.value = false
  }
}

async function loadProjectDefault() {
  if (!currentProjectId.value) return
  try {
    const p = await apiGet<any>(`/api/projects/${currentProjectId.value}`)
    if (p) {
      projectDefaultPov.value = p.narrative_pov || '第三人称'
      projectDefaultStyleName.value = p.writing_style?.name || ''
    }
  } catch {}
}

async function checkActiveTask() {
  try {
    const t = await api.getActiveBatchTask()
    if (t && ['pending', 'running'].includes(t.status)) {
      currentTask.value = t
      startPolling(t.id)
    }
  } catch {}
}

async function onSubmit() {
  if (!startChapterNumber.value || startChapterNumber.value < 1) {
    msg.warning('请选择起始章节')
    return
  }
  if (actualCount.value <= 0) {
    msg.warning('没有可用的空章节')
    return
  }
  submitting.value = true
  try {
    if (import.meta.client) localStorage.setItem('moyu_chapter_words', String(targetWords.value))
    const r = await api.batchGenerate({
      start_chapter_number: startChapterNumber.value,
      count: actualCount.value,
      enable_analysis: enableAnalysis.value,
      target_word_count: targetWords.value,
      model_override: aiModel.value || undefined,
      style_id: styleId.value || undefined,
      narrative_perspective: narrativePerspective.value || undefined,
    })
    msg.success(`已提交批量生成任务，从第${startChapterNumber.value}章起共 ${actualCount.value} 章`)
    currentTask.value = await api.getBatchStatus(r.task_id)
    startPolling(r.task_id)
  } catch (e: any) {
    msg.error('提交失败：' + formatError(e))
  } finally {
    submitting.value = false
  }
}

function startPolling(taskId: number) {
  stopPolling()
  const poll = async () => {
    try {
      const t = await api.getBatchStatus(taskId)
      currentTask.value = t
        if (t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled') {
          stopPolling()
          if (t.status === 'completed') {
            msg.success(`批量生成完成：${t.completed_chapters}/${t.total_chapters} 章`)
            emit('done')
          }
        }
    } catch (e) {
      console.warn('轮询失败', e)
    }
  }
  poll()
  pollTimer = setInterval(poll, 3000)
}
function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

async function onCancel() {
  if (!currentTask.value) return
  if (!await msg.confirm('确认取消批量生成？')) return
  stopPolling()
  const taskId = currentTask.value.id
  currentTask.value = null
  try {
    await api.cancelBatchTask(taskId)
    msg.success('已取消')
    emit('done')  // 通知父组件刷新，让已生成的章节不再出现在空章节列表
  } catch (e: any) {
    msg.error('取消失败：' + formatError(e))
  }
}

onUnmounted(() => stopPolling())

const statusMeta = (s: string) => {
  const map: Record<string, { label: string; color: string }> = {
    pending: { label: '等待中', color: '#D49A4E' },
    running: { label: '生成中', color: '#4D8088' },
    completed: { label: '已完成', color: '#52A569' },
    failed: { label: '失败', color: '#C75B5B' },
    cancelled: { label: '已取消', color: '#8C8C8C' },
  }
  return map[s] || { label: s, color: '#8C8C8C' }
}
</script>

<template>
  <span>
    <a-button type="primary" @click="openPanel">📚 批量生成</a-button>

    <a-modal v-model:open="open" title="批量生成章节" width="680px" :footer="null">
      <!-- 任务进行中 -->
      <div v-if="currentTask && ['pending', 'running'].includes(currentTask.status)" class="task-active">
        <div class="task-header">
          <span class="task-status-tag" :style="{ background: statusMeta(currentTask.status).color + '20', color: statusMeta(currentTask.status).color }">
            {{ statusMeta(currentTask.status).label }}
          </span>
          <span class="task-progress-text">{{ currentTask.completed_chapters }}/{{ currentTask.total_chapters }} 章</span>
          <a-button danger size="small" style="margin-left:auto" @click="onCancel">取消生成</a-button>
        </div>
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: currentTask.progress + '%', background: statusMeta(currentTask.status).color }"></div>
        </div>
        <div class="task-message">{{ currentTask.status_message || '处理中…' }}</div>
        <div v-if="currentTask.current_chapter_number" class="current-chap">
          正在生成：第 {{ currentTask.current_chapter_number }} 章
          <span v-if="currentTask.current_retry_count > 0" class="retry-badge">重试 {{ currentTask.current_retry_count }}</span>
        </div>
      </div>

      <!-- 任务完成/失败 -->
      <a-alert
        v-else-if="currentTask && ['completed', 'failed', 'cancelled'].includes(currentTask.status)"
        :type="currentTask.status === 'completed' ? 'success' : currentTask.status === 'failed' ? 'error' : 'warning'"
        show-icon
        style="margin-bottom: 16px"
      >
        <template #message>
          {{ statusMeta(currentTask.status).label }}：{{ currentTask.completed_chapters }}/{{ currentTask.total_chapters }} 章完成
        </template>
        <template v-if="currentTask.failed_chapters?.length" #description>
          失败章节：
          <span v-for="f in currentTask.failed_chapters" :key="f.chapter_id">
            第{{ f.chapter_number }}章（{{ f.error?.slice(0, 40) }}）；
          </span>
        </template>
      </a-alert>

      <!-- 配置表单 -->
      <div v-if="!currentTask || ['completed', 'failed', 'cancelled'].includes(currentTask.status)" class="config-section">
        <a-alert type="info" show-icon style="margin-bottom:16px;" message="严格按序生成 | 从起始章起连续生成 N 章 | 任一失败则终止" />

        <!-- 起始章 + 数量 -->
        <div class="form-row-2">
          <div class="form-col">
            <label class="form-label">起始章节</label>
            <a-select v-model:value="startChapterNumber" style="width:100%" placeholder="选择起始章">
              <a-select-option v-for="c in emptyChapters" :key="c.id" :value="c.chapter_number">
                第{{ c.chapter_number }}章：{{ c.title || '无标题' }}
              </a-select-option>
            </a-select>
            <div class="field-hint">从该章起连续生成（只列出空章节）</div>
          </div>
          <div class="form-col">
            <label class="form-label">生成数量</label>
            <a-radio-group v-model:value="count" button-style="solid" style="width:100%">
              <a-radio-button v-for="n in countOptions" :key="n" :value="n" :style="{ width: (100 / countOptions.length) + '%' }">{{ n }} 章</a-radio-button>
            </a-radio-group>
            <div class="field-hint">
              可用空章节 {{ availableCount }} 章
              <template v-if="actualCount < count">，实际将生成 {{ actualCount }} 章</template>
              <template v-else>，将生成第 {{ startChapterNumber }} ~ {{ (startChapterNumber || 1) + actualCount - 1 }} 章</template>
            </div>
          </div>
        </div>

        <!-- 风格 + 字数 -->
        <div class="form-row-2">
          <div class="form-col">
            <label class="form-label">写作风格</label>
            <a-select v-model:value="styleId" style="width:100%" placeholder="项目默认风格" allow-clear show-search option-filter-prop="label">
              <a-select-option v-for="s in writingStyles" :key="s.id" :value="s.id" :label="s.name + (projectDefaultStyleName === s.name ? ' (默认)' : '')">
                {{ s.name }}{{ projectDefaultStyleName === s.name ? ' (项目默认)' : '' }}
              </a-select-option>
            </a-select>
          </div>
          <div class="form-col">
            <label class="form-label">目标字数</label>
            <a-input-number v-model:value="targetWords" :min="500" :max="10000" :step="100" style="width:100%" />
          </div>
        </div>

        <!-- 模型 + 视角 -->
        <div class="form-row-2">
          <div class="form-col">
            <label class="form-label">AI 模型</label>
            <a-select
              v-model:value="aiModel"
              style="width:100%"
              :placeholder="defaultModelName ? `使用默认（${defaultModelName}）` : '使用默认模型'"
              allow-clear show-search option-filter-prop="label"
              :loading="loadingModels"
            >
              <a-select-option value="">使用默认模型</a-select-option>
              <a-select-option v-for="m in remoteModels" :key="m.id" :value="m.id" :label="m.id">{{ m.id }}</a-select-option>
            </a-select>
          </div>
          <div class="form-col">
            <label class="form-label">叙事视角</label>
            <a-select v-model:value="narrativePerspective" style="width:100%" :placeholder="`按小说设定（${projectDefaultPov}）`" allow-clear>
              <a-select-option value="">按小说设定</a-select-option>
              <a-select-option value="第三人称">第三人称（他/她）</a-select-option>
              <a-select-option value="第一人称">第一人称（我）</a-select-option>
              <a-select-option value="全知视角">全知视角</a-select-option>
            </a-select>
          </div>
        </div>

        <div class="options">
          <a-checkbox v-model:checked="enableAnalysis">生成后自动剧情分析</a-checkbox>
        </div>

        <div class="submit-bar">
          <a-button type="primary" :loading="submitting" :disabled="actualCount <= 0" @click="onSubmit">
            开始批量生成（{{ actualCount }} 章）
          </a-button>
          <span class="hint">提示：按章节顺序逐个生成，前一章完成后才生成下一章</span>
        </div>
      </div>
    </a-modal>
  </span>
</template>

<style scoped>
.task-active { background: #F8F6F1; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.task-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.task-status-tag { font-size: 12px; padding: 2px 10px; border-radius: 4px; font-weight: 600; }
.task-progress-text { font-size: 14px; font-weight: 600; color: #2B2B2B; }
.progress-bar { height: 6px; background: #E8E4DC; border-radius: 999; overflow: hidden; margin-bottom: 10px; }
.progress-fill { height: 100%; border-radius: 999; transition: width .5s; }
.task-message { font-size: 13px; color: #595959; }
.current-chap { font-size: 12px; color: #4D8088; margin-top: 6px; font-weight: 500; }
.retry-badge { background: #FFF7E6; color: #D49A4E; padding: 1px 6px; border-radius: 4px; font-size: 11px; margin-left: 6px; }
.config-section { }
.form-row-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px; }
.form-col { display: flex; flex-direction: column; gap: 4px; }
.form-label { font-size: 13px; color: #595959; font-weight: 500; }
.field-hint { font-size: 11px; color: #999; }
.options { margin-bottom: 14px; }
.submit-bar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.hint { font-size: 12px; color: #8C8C8C; }
@media(max-width: 600px) { .form-row-2 { grid-template-columns: 1fr; } }
</style>
