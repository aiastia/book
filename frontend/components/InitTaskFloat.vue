<script setup lang="ts">
// 全局浮动任务面板：对标 MuMuAINovel FloatingTaskPanel
// 展示所有后台任务（通用队列 + 旧项目初始化）
// 任务完成后保留至用户手动关闭
import { apiGet, apiPost } from '~/composables/useApi'

const emit = defineEmits<{ (e: 'retry', task: any): void }>()

const { tasks, isActive, hasAnyTasks, refreshTasks, cancelTask, dismissTask, clearDoneTasks, trackTask, taskStatus: legacyTaskStatus, startLegacy } = useBackgroundTasks()
const msg = useMessage()
const collapsed = ref(true)
const resuming = ref(false)

async function retryTask(t: any) {
  if (t.task_type === 'chapter_batch') {
    dismissTask(t.id)
    // 批量生成有专用重试 API（清空失败章节）
    apiPost(`/api/projects/${t.project_id}/batch-generate/${t.id}/retry`, {})
      .then((r: any) => {
        if (r?.task_id) {
          trackTask({ id: r.bg_task_id || r.task_id, task_type: 'chapter_batch', title: `重试批量生成（${r.total || '?'}章）` })
          msg.success(`已重新提交（清空 ${r.cleared_chapters || 0} 个失败章节）`)
        } else {
          msg.error('重试失败：未返回任务ID')
        }
      })
      .catch((e: any) => msg.error('重试失败：' + formatError(e)))
  } else {
    // 通用重试：用原 payload 重新提交
    dismissTask(t.id)
    try {
      const r = await apiPost<any>(`/api/tasks/${t.id}/retry`, {})
      if (r?.task_id) {
        trackTask({ id: r.task_id, task_type: t.task_type, title: `重试：${t.title || t.task_type}` })
        msg.success('已重新提交任务')
      }
    } catch (e: any) {
      msg.error('重试失败：' + formatError(e))
      // 重试失败时恢复任务显示
      t._dismissed = false
    }
  }
}
const failedTasks = ref<any[]>([])
const ignoredTaskIds = ref<Set<number>>(new Set())

watch(isActive, (v) => { if (v) collapsed.value = false })  // 新任务来时展开面板

// 旧 init-task 失败时刷新失败列表
watch(legacyTaskStatus, (s) => {
  if (s?.status === 'failed') loadFailedTasks()
})

// 加载失败的任务
async function loadFailedTasks() {
  // 没登录态时跳过（避免 401）
  if (import.meta.client && !localStorage.getItem('moyu_token')) return
  try {
    const data = await apiGet<any[]>('/api/projects/init-tasks/failed', { timeout: 5000 })
    failedTasks.value = (data || []).filter(t => !ignoredTaskIds.value.has(t.id))
  } catch (e: any) {
    // 静默失败：未登录或接口异常时不影响页面
    if (String(e).includes('401') || String(e).includes('403')) return
    console.warn('加载失败任务失败', e?.message || e)
  }
}

// 忽略失败任务
function ignoreTask(taskId: number) {
  ignoredTaskIds.value.add(taskId)
  if (import.meta.client) {
    const ignored = Array.from(ignoredTaskIds.value)
    localStorage.setItem('moyu_ignored_tasks', JSON.stringify(ignored))
  }
  failedTasks.value = failedTasks.value.filter(t => t.id !== taskId)
}

// 恢复失败任务
	async function onResume(taskId: number | string) {
	  resuming.value = true
	  try {
	    const numericId = typeof taskId === 'string' ? parseInt(taskId.replace('legacy-', '')) : taskId
	    console.log('[InitTaskFloat] Resuming task:', numericId)
	    if (!numericId || numericId <= 0) {
	      msg.error('任务 ID 无效，请刷新页面后重试')
	      resuming.value = false
	      return
	    }
    const result = await apiPost<any>(`/api/projects/init-task/${numericId}/resume`, {}, { timeout: 10000 })
    console.log('[InitTaskFloat] Resume result:', result)
    msg.success('任务已恢复执行')
    failedTasks.value = failedTasks.value.filter(t => t.id !== numericId)
    startLegacy(numericId)
  } catch (e: any) {
    console.error('resume failed', e)
    msg.error('重试失败：' + (e.message || '未知错误'))
  } finally {
    resuming.value = false
  }
}

// 页面加载时检查失败任务
onMounted(() => {
  if (import.meta.client) {
    const saved = localStorage.getItem('moyu_ignored_tasks')
    if (saved) {
      try {
        ignoredTaskIds.value = new Set(JSON.parse(saved))
      } catch {}
    }
  }
  loadFailedTasks()
})

const statusMeta = (s: string) => {
  if (s === 'completed') return { text: '已完成', color: '#52A569', icon: '\u2713' }
  if (s === 'failed') return { text: '失败', color: '#C75B5B', icon: '\u2715' }
  if (s === 'cancelled') return { text: '已取消', color: '#8C8C8C', icon: '\u25cb' }
  if (s === 'running') return { text: '进行中', color: '#4D8088', icon: '\u21bb' }
  return { text: '等待中', color: '#D49A4E', icon: '\u2026' }
}

const taskTypeIcon: Record<string, string> = {
  init: '\u2699\ufe0f',
  world: '\U0001f310',
  organizations: '\U0001f3db',
  characters: '\U0001f465',
  outline: '\U0001f4cb',
  chapter_generate: '\u270d\ufe0f',
  chapter_batch: '\U0001f4da',
  chapter_analyze: '\U0001f50d',
  chapter_batch_analyze: '\U0001f50d',
  outline_new: '\U0001f4cb',
  outline_continue: '\u27a1\ufe0f',
  book_import: '\U0001f4d6',
}
const typeLabel: Record<string, string> = {
  init: '项目初始化',
  world: '世界观生成',
  organizations: '组织生成',
  characters: '角色生成',
  outline: '大纲生成',
  chapter_generate: '章节生成',
  chapter_batch: '批量生成',
  chapter_analyze: '剧情分析',
  chapter_batch_analyze: '批量分析',
  outline_new: '大纲生成',
  outline_continue: '大纲续写',
  book_import: '拆书导入',
}

function tagStyle(status: string) {
  const m = statusMeta(status)
  return { background: m.color + '20', color: m.color, borderColor: m.color + '40' }
}

function formatTime(ts: number | undefined) {
  if (!ts) return ''
  const d = new Date(ts)
  const h = d.getHours().toString().padStart(2, '0')
  const m = d.getMinutes().toString().padStart(2, '0')
  return `${h}:${m}`
}

function parseSubProgress(t: any) {
  if (!t.progress_details) return null
  if (typeof t.progress_details === 'object') return t.progress_details
  try { return JSON.parse(t.progress_details) } catch { return null }
}

// 是否有已完成/失败的任务
const hasDoneTasks = computed(() =>
  tasks.value.some(t => t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled')
)

</script>

<template>
  <!-- 始终渲染浮窗，有任务时默认折叠，无任务时仅显示标题栏 -->
  <div class="float-panel" :class="{ collapsed }">
    <div class="float-head" @click="collapsed = !collapsed">
      <span class="float-title-icon">&#x2699;&#xFE0F;</span>
      <span class="float-title">后台任务</span>
      <span v-if="failedTasks.length" class="float-badge warning">{{ failedTasks.length }} 个失败</span>
      <span v-else-if="isActive" class="float-badge">{{ tasks.length }} 个</span>
      <span v-else-if="hasDoneTasks" class="float-badge done">{{ tasks.length }} 个已完成</span>
      <a-button size="small" type="link" @click.stop="refreshTasks()" :style="{ marginLeft: '8px', padding: '0 4px' }" title="刷新">&#x21BB;</a-button>
      <span class="float-toggle">{{ collapsed ? '&#9650;' : '&#9660;' }}</span>
    </div>
    <div v-show="!collapsed" class="float-body">
      <!-- 失败任务提示 -->
      <div v-if="failedTasks.length" class="failed-section">
        <div class="failed-section-title">
          <span>&#x26A0;&#xFE0F; 有 {{ failedTasks.length }} 个任务需要处理</span>
        </div>
        <div v-for="task in failedTasks" :key="task.id" class="failed-task-item">
          <div class="failed-task-info">
            <div class="failed-task-title">项目 #{{ task.project_id }}</div>
            <div class="failed-task-msg">{{ task.status_message }}</div>
          </div>
          <div class="failed-task-actions">
            <a-button type="primary" size="small" :loading="resuming" @click.stop="onResume(task.id)">
              重试
            </a-button>
            <a-button size="small" @click.stop="ignoreTask(task.id)">
              忽略
            </a-button>
          </div>
        </div>
      </div>

      <!-- 活跃任务列表 -->
      <div v-for="t in tasks" :key="t.id" class="task-row" :class="{ done: t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled' }">
        <div class="task-status">
          <span class="task-tag" :style="tagStyle(t.status)">
            {{ statusMeta(t.status).icon }} {{ statusMeta(t.status).text }}
          </span>
          <span class="task-type">
            <span class="type-icon">{{ taskTypeIcon[t.task_type] || '&#x2699;&#xFE0F;' }}</span>
            {{ t.title || typeLabel[t.task_type] || t.task_type }}
          </span>
          <span v-if="t._doneAt && t.status !== 'pending' && t.status !== 'running'" class="task-time">{{ formatTime(t._doneAt) }}</span>
        </div>
        <div class="task-msg">{{ t.status_message || '准备中...' }}</div>
        <div v-if="t.status === 'failed' && t.error" class="task-error">{{ typeof t.error === 'string' ? t.error : JSON.stringify(t.error) }}</div>
        <!-- 阶段标签 -->
        <div v-if="parseSubProgress(t)?.phase && (t.status === 'pending' || t.status === 'running')" class="task-phase">
          {{ parseSubProgress(t).phase === 'generating' ? '✍️ 生成中' : parseSubProgress(t).phase === 'analyzing' ? '🔍 分析中' : '' }}
        </div>
        <!-- 批量任务子进度：生成 / 分析 -->
        <div v-if="parseSubProgress(t) && (t.status === 'pending' || t.status === 'running')" class="task-sub-progress">
          <div v-if="parseSubProgress(t)?.generation?.total" class="sub-row">
            <span class="sub-label">✍️ 生成</span>
            <div class="sub-track">
              <div class="sub-fill gen" :style="{ width: ((parseSubProgress(t).generation.done || 0) / (parseSubProgress(t).generation.total || 1) * 100) + '%' }"></div>
            </div>
            <span class="sub-num">{{ parseSubProgress(t).generation.done || 0 }}/{{ parseSubProgress(t).generation.total }}</span>
          </div>
          <div v-if="parseSubProgress(t)?.analysis?.total" class="sub-row">
            <span class="sub-label">🔍 分析</span>
            <div class="sub-track">
              <div class="sub-fill ana" :style="{ width: ((parseSubProgress(t).analysis.done || 0) / (parseSubProgress(t).analysis.total || 1) * 100) + '%' }"></div>
            </div>
            <span class="sub-num">{{ parseSubProgress(t).analysis.done || 0 }}/{{ parseSubProgress(t).analysis.total }}</span>
          </div>
        </div>
        <div class="task-progress" v-if="t.status === 'pending' || t.status === 'running'">
          <div class="progress-track">
            <div class="progress-fill" :style="{ width: (t.progress || 0) + '%', background: statusMeta(t.status).color }"></div>
          </div>
          <span class="progress-num">{{ t.progress || 0 }}%</span>
        </div>
        <!-- 旧 init-task 的步骤展示 -->
        <div v-if="t._steps && t._isLegacy" class="task-steps">
          <span v-for="(s, i) in t._steps" :key="i"
            class="step-item"
            :class="{ done: s.done, failed: t._failedStep && t.status === 'failed' && !s.done }">
            <span class="step-icon">{{ s.done ? '&#10003;' : (t._failedStep && t.status === 'failed' ? '&#9888;' : '&#8226;') }}</span>{{ s.label }}
          </span>
        </div>
        <!-- 操作按钮 -->
        <div class="task-actions">
          <a-button
            v-if="t._isLegacy && t.status === 'failed'"
            size="small" type="primary" :loading="resuming"
            @click.stop="onResume(t._taskId || t.id)"
          >从失败处重试</a-button>
          <a-button
            v-if="!t._isLegacy && t.status === 'failed'"
            size="small" type="primary"
            @click.stop="retryTask(t)"
          >重试</a-button>
          <a-button
            v-if="t.status === 'pending' || t.status === 'running'"
            size="small" danger type="link" @click.stop="cancelTask(t.id)"
          >取消</a-button>
          <a-button
            v-if="t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled'"
            size="small" type="link" @click.stop="dismissTask(t.id)"
          >关闭</a-button>
        </div>
      </div>

      <!-- 清空已完成任务 -->
      <div v-if="hasDoneTasks && !isActive" class="clear-row">
        <a-button size="small" type="link" @click="clearDoneTasks">清空已完成任务</a-button>
      </div>

      <!-- 空状态提示 -->
      <div v-if="!tasks.length && !failedTasks.length" class="empty-hint">
        暂无后台任务
      </div>
    </div>
  </div>
</template>

<style scoped>
.float-panel { position: fixed; bottom: 24px; right: 24px; z-index: 1000; width: 360px; background: #fff; border-radius: 12px; box-shadow: 0 8px 32px rgba(43,43,43,0.18); border: 1px solid #E8E4DC; overflow: hidden; transition: all 0.3s ease; }
.float-panel.collapsed { width: 220px; }
.float-head { display: flex; align-items: center; gap: 8px; padding: 10px 14px; cursor: pointer; border-bottom: 1px solid #F0EDE6; background: #FAFAF7; }
.float-panel.collapsed .float-head { border-bottom: none; }
.float-title-icon { font-size: 14px; }
.float-title { font-size: 13px; font-weight: 600; color: #2B2B2B; }
.float-badge { margin-left: auto; background: #4D8088; color: #fff; font-size: 11px; padding: 1px 7px; border-radius: 10px; font-weight: 600; }
.float-badge.warning { background: #D49A4E; }
.float-badge.done { background: #52A569; }
.float-toggle { margin-left: 4px; color: #8C8C8C; font-size: 11px; }
.float-panel:not(.collapsed) .float-toggle { margin-left: 0; }
.float-body { padding: 8px 14px 12px; max-height: 380px; overflow-y: auto; }

/* 失败任务区域 */
.failed-section { margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #F0EDE6; }
.failed-section-title { font-size: 12px; font-weight: 600; color: #D49A4E; margin-bottom: 8px; }
.failed-task-item { background: #FFF8F0; border: 1px solid #FFE0B2; border-radius: 8px; padding: 10px; margin-bottom: 8px; }
.failed-task-info { margin-bottom: 8px; }
.failed-task-title { font-size: 13px; font-weight: 600; color: #2B2B2B; margin-bottom: 4px; }
.failed-task-msg { font-size: 12px; color: #666; }
.failed-task-actions { display: flex; gap: 8px; }

/* 任务行 */
.task-row { padding: 10px 0; border-bottom: 1px solid #F5F2EB; }
.task-row:last-child { border-bottom: none; }
.task-row.done { opacity: 0.85; }
.task-status { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }
.task-tag { font-size: 11px; padding: 2px 8px; border-radius: 4px; border: 1px solid; font-weight: 500; }
.task-type { font-size: 12px; color: #4D8088; background: #EAF0F1; padding: 2px 8px; border-radius: 4px; display: inline-flex; align-items: center; gap: 4px; }
.type-icon { font-size: 12px; }
.task-time { font-size: 11px; color: #8C8C8C; margin-left: auto; }
.task-msg { font-size: 13px; color: #595959; margin-bottom: 8px; line-height: 1.5; }
.task-error { font-size: 12px; color: #C75B5B; margin-bottom: 8px; padding: 6px 8px; background: #FFF0F0; border-radius: 4px; border-left: 3px solid #C75B5B; line-height: 1.5; word-break: break-all; }
.task-phase { font-size: 11px; color: #4D8088; font-weight: 500; margin-bottom: 4px; }
.task-progress { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.progress-track { flex: 1; height: 5px; background: #F0EDE6; border-radius: 999; overflow: hidden; }
.progress-fill { height: 100%; border-radius: 999; transition: width .5s; }
.progress-num { font-size: 11px; color: #8C8C8C; min-width: 32px; text-align: right; }
.task-steps { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 6px; }
.step-item { display: flex; align-items: center; gap: 3px; font-size: 11px; padding: 2px 8px; border-radius: 4px; background: #F8F6F1; color: #8C8C8C; }
.step-item.done { background: #EAF0F1; color: #4D8088; font-weight: 500; }
.step-item.failed { background: #FFF0F0; color: #C75B5B; font-weight: 500; }
.step-icon { font-size: 10px; }
.task-actions { display: flex; justify-content: flex-end; gap: 4px; }
/* 子进度条（批量任务生成/分析分开展示） */
.task-sub-progress { margin-bottom: 6px; padding-left: 4px; }
.sub-row { display: flex; align-items: center; gap: 6px; margin-bottom: 3px; }
.sub-label { font-size: 11px; color: #8C8C8C; min-width: 42px; }
.sub-track { flex: 1; height: 4px; background: #F0EDE6; border-radius: 999; overflow: hidden; }
.sub-fill.gen { height: 100%; background: #4D8088; border-radius: 999; transition: width .5s; }
.sub-fill.ana { height: 100%; background: #D49A4E; border-radius: 999; transition: width .5s; }
.sub-num { font-size: 10px; color: #8C8C8C; min-width: 36px; text-align: right; }
.clear-row { text-align: center; padding: 8px 0 4px; }
.empty-hint { font-size: 12px; color: #8C8C8C; text-align: center; padding: 12px 0; }
</style>
