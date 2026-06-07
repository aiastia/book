<script setup lang="ts">
// 批量生成面板（#12）：章节多选 + 提交 + 进度轮询 + 取消
import { useProjectApi } from '~/composables/useProjectApi'
import { useProject } from '~/composables/useProject'
import { useBackgroundTasks } from '~/composables/useBackgroundTasks'

const props = defineProps<{
  chapters: any[]
}>()
const emit = defineEmits<{ (e: 'done'): void }>()

const api = useProjectApi()
const msg = useMessage()
const { trackTask } = useBackgroundTasks()

const open = ref(false)
const selectedIds = ref<number[]>([])
const enableAnalysis = ref(true)
const submitting = ref(false)

// 当前任务状态
const currentTask = ref<any>(null)
const polling = ref(false)
let pollTimer: any = null

const total = computed(() => props.chapters?.length || 0)

// 可批量生成的章节（未生成内容 + 状态为 draft）
const generatableChapters = computed(() => {
  return (props.chapters || []).filter((c: any) => {
    return !c.content || c.content.trim().length < 100
  })
})

function toggleSelect(id: number) {
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) selectedIds.value.splice(idx, 1)
  else selectedIds.value.push(id)
}
function selectAll() {
  selectedIds.value = generatableChapters.value.map((c: any) => c.id)
}
function selectNone() {
  selectedIds.value = []
}

function openPanel() {
  // 启动时检查是否有进行中的任务
  checkActiveTask()
  open.value = true
}

async function checkActiveTask() {
  try {
    const t = await api.getActiveBatchTask()
    if (t) {
      currentTask.value = t
      startPolling(t.id)
    }
  } catch {}
}

async function onSubmit() {
  if (!selectedIds.value.length) {
    msg.warning('请选择至少一个章节')
    return
  }
  submitting.value = true
  try {
    const r = await api.batchGenerate({
      chapter_ids: selectedIds.value,
      enable_analysis: enableAnalysis.value,
    })
    msg.success(`已提交批量生成任务，共 ${r.total} 章`)
    // 立即查询任务状态
    currentTask.value = await api.getBatchStatus(r.task_id)
    startPolling(r.task_id)
    selectedIds.value = []
  } catch (e: any) {
    msg.error('提交失败：' + formatError(e))
  } finally {
    submitting.value = false
  }
}

function startPolling(taskId: number) {
  stopPolling()
  polling.value = true
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
  polling.value = false
}

async function onCancel() {
  if (!currentTask.value) return
  if (!await msg.confirm('确认取消批量生成？')) return
  try {
    await api.cancelBatchTask(currentTask.value.id)
    msg.success('已请求取消')
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

      <!-- 选择章节 -->
      <div v-if="!currentTask || ['completed', 'failed', 'cancelled'].includes(currentTask.status)" class="select-section">
        <div class="select-header">
          <span class="select-title">选择要生成的章节（{{ selectedIds.length }}/{{ generatableChapters.length }}）</span>
          <div>
            <a-button type="link" size="small" @click="selectAll">全选</a-button>
            <a-button type="link" size="small" @click="selectNone">清空</a-button>
          </div>
        </div>
        <div class="chap-select-list">
          <div v-if="!generatableChapters.length" class="empty-hint">没有待生成的章节（所有章节已有内容）</div>
          <div
            v-for="c in generatableChapters" :key="c.id"
            class="chap-select-item"
            :class="{ selected: selectedIds.includes(c.id) }"
            @click="toggleSelect(c.id)"
          >
            <span class="check">{{ selectedIds.includes(c.id) ? '☑' : '☐' }}</span>
            <span class="chap-num">第{{ c.chapter_number }}章</span>
            <span class="chap-title">{{ c.title }}</span>
          </div>
        </div>

        <div class="options">
          <a-checkbox v-model:checked="enableAnalysis">生成后自动剧情分析</a-checkbox>
        </div>

        <div class="submit-bar">
          <a-button type="primary" :loading="submitting" :disabled="!selectedIds.length" @click="onSubmit">
            开始批量生成（{{ selectedIds.length }} 章）
          </a-button>
          <span class="hint">提示：将按章节顺序逐个生成，前一章完成后才生成下一章</span>
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
.select-section { }
.select-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.select-title { font-size: 13px; font-weight: 600; color: #2B2B2B; }
.chap-select-list { max-height: 280px; overflow-y: auto; border: 1px solid #E8E4DC; border-radius: 8px; padding: 8px; margin-bottom: 12px; }
.empty-hint { text-align: center; color: #8C8C8C; padding: 24px 0; font-size: 13px; }
.chap-select-item { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 6px; cursor: pointer; transition: background .15s; }
.chap-select-item:hover { background: #F8F6F1; }
.chap-select-item.selected { background: #EAF0F1; }
.check { font-size: 16px; color: #4D8088; }
.chap-num { font-size: 12px; color: #8C8C8C; min-width: 60px; }
.chap-title { font-size: 13px; color: #2B2B2B; }
.options { margin-bottom: 14px; }
.submit-bar { display: flex; align-items: center; gap: 12px; }
.hint { font-size: 12px; color: #8C8C8C; }
</style>
