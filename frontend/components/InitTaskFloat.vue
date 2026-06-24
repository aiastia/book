<script setup lang="ts">
// 全局浮动任务面板：对标 MuMuAINovel FloatingTaskPanel
// 展示所有后台任务（通用队列 + 旧项目初始化）
import { apiGet, apiPost } from '~/composables/useApi'

const { tasks, isActive, cancelTask, dismissTask } = useBackgroundTasks()
const msg = useMessage()
const collapsed = ref(true)
const resuming = ref(false)
const failedTasks = ref<any[]>([])
const ignoredTaskIds = ref<Set<number>>(new Set())

watch(isActive, (v) => { if (v) collapsed.value = true })  // 新任务来时保持折叠（小条），避免遮挡操作区

// 加载失败的任务
async function loadFailedTasks() {
  try {
    const data = await apiGet<any[]>('/api/projects/init-tasks/failed', { timeout: 5000 })
    failedTasks.value = (data || []).filter(t => !ignoredTaskIds.value.has(t.id))
  } catch (e) {
    console.warn('加载失败任务失败', e)
  }
}

// 忽略失败任务
function ignoreTask(taskId: number) {
  ignoredTaskIds.value.add(taskId)
  // 保存到 localStorage
  if (import.meta.client) {
    const ignored = Array.from(ignoredTaskIds.value)
    localStorage.setItem('moyu_ignored_tasks', JSON.stringify(ignored))
  }
  // 从列表中移除
  failedTasks.value = failedTasks.value.filter(t => t.id !== taskId)
}

// 恢复失败任务
async function onResume(taskId: number | string) {
  resuming.value = true
  try {
    const numericId = typeof taskId === 'string' ? parseInt(taskId.replace('legacy-', '')) : taskId
    console.log('[InitTaskFloat] Resuming task:', numericId)
    const result = await apiPost<any>(`/api/projects/init-task/${numericId}/resume`, {}, { timeout: 10000 })
    console.log('[InitTaskFloat] Resume result:', result)
    msg.success('任务已恢复执行')
    // 从失败列表中移除
    failedTasks.value = failedTasks.value.filter(t => t.id !== numericId)
    // 启动轮询以显示进度
    startPollingForTask(numericId)
  } catch (e: any) {
    console.error('resume failed', e)
    msg.error('重试失败：' + (e.message || '未知错误'))
  } finally {
    resuming.value = false
  }
}

// 为恢复的任务启动轮询
function startPollingForTask(taskId: number) {
  // 添加到 tasks 列表中显示进度
  const existing = tasks.value.find(t => t.id === `legacy-${taskId}`)
  if (!existing) {
    tasks.value.push({
      id: `legacy-${taskId}`,
      task_type: 'init',
      title: '项目初始化',
      status: 'running',
      progress: 0,
      status_message: '正在恢复...',
      _source: 'legacy',
      _isLegacy: true,
      _taskId: taskId,
    })
  }
}

// 页面加载时检查失败任务
onMounted(() => {
  // 恢复忽略的任务列表
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

</script>

<template>
  <!-- 无任务时不渲染，避免遮挡页面操作区 -->
  <div v-if="isActive || failedTasks.length" class="float-panel" :class="{ collapsed }">
    <div class="float-head" @click="collapsed = !collapsed">
      <span class="float-title-icon">&#x2699;&#xFE0F;</span>
      <span class="float-title">后台任务</span>
      <span v-if="failedTasks.length" class="float-badge warning">{{ failedTasks.length }} 个失败</span>
      <span v-else-if="isActive" class="float-badge">{{ tasks.length }} 个</span>
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
      <div v-for="t in tasks" :key="t.id" class="task-row">
        <div class="task-status">
          <span class="task-tag" :style="tagStyle(t.status)">
            {{ statusMeta(t.status).icon }} {{ statusMeta(t.status).text }}
          </span>
          <span class="task-type">
            <span class="type-icon">{{ taskTypeIcon[t.task_type] || '&#x2699;&#xFE0F;' }}</span>
            {{ t.title || typeLabel[t.task_type] || t.task_type }}
          </span>
        </div>
        <div class="task-msg">{{ t.status_message || '准备中...' }}</div>
        <div class="task-progress">
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
            v-if="t.status === 'pending' || t.status === 'running'"
            size="small" danger type="link" @click.stop="cancelTask(t.id)"
          >取消</a-button>
          <a-button
            v-if="t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled'"
            size="small" type="link" @click.stop="dismissTask(t.id)"
          >关闭</a-button>
        </div>
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
.float-panel.collapsed { width: 200px; }
.float-head { display: flex; align-items: center; gap: 8px; padding: 10px 14px; cursor: pointer; border-bottom: 1px solid #F0EDE6; background: #FAFAF7; }
.float-panel.collapsed .float-head { border-bottom: none; }
.float-title-icon { font-size: 14px; }
.float-title { font-size: 13px; font-weight: 600; color: #2B2B2B; }
.float-badge { margin-left: auto; background: #4D8088; color: #fff; font-size: 11px; padding: 1px 7px; border-radius: 10px; font-weight: 600; }
.float-badge.warning { background: #D49A4E; }
.float-toggle { margin-left: auto; color: #8C8C8C; font-size: 11px; }
.float-panel:not(.collapsed) .float-toggle { margin-left: 0; }
.float-body { padding: 8px 14px 12px; max-height: 360px; overflow-y: auto; }

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
.task-status { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }
.task-tag { font-size: 11px; padding: 2px 8px; border-radius: 4px; border: 1px solid; font-weight: 500; }
.task-type { font-size: 12px; color: #4D8088; background: #EAF0F1; padding: 2px 8px; border-radius: 4px; display: inline-flex; align-items: center; gap: 4px; }
.type-icon { font-size: 12px; }
.task-msg { font-size: 13px; color: #595959; margin-bottom: 8px; line-height: 1.5; }
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
.empty-hint { font-size: 12px; color: #8C8C8C; text-align: center; padding: 12px 0; }
</style>
