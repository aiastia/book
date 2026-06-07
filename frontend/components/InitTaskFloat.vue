<script setup lang="ts">
// 全局浮动任务面板：对标 MuMuAINovel FloatingTaskPanel
// 展示所有后台任务（通用队列 + 旧项目初始化）
const { tasks, isActive, cancelTask, dismissTask } = useBackgroundTasks()
const collapsed = ref(false)
watch(isActive, (v) => { if (v) collapsed.value = false })

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
  <div v-if="isActive || tasks.length" class="float-panel" :class="{ collapsed }">
    <div class="float-head" @click="collapsed = !collapsed">
      <span class="float-title-icon">&#x2699;&#xFE0F;</span>
      <span class="float-title">后台任务</span>
      <span v-if="isActive" class="float-badge">{{ tasks.length }} 个</span>
      <span class="float-toggle">{{ collapsed ? '&#9650;' : '&#9660;' }}</span>
    </div>
    <div v-show="!collapsed" class="float-body">
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
          <span v-for="(s, i) in t._steps" :key="i" class="step-item" :class="{ done: s.done }">
            <span class="step-icon">{{ s.done ? '&#10003;' : '&#8226;' }}</span>{{ s.label }}
          </span>
        </div>
        <!-- 操作按钮 -->
        <div class="task-actions">
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
      <div v-if="!tasks.length" class="empty-hint">暂无后台任务</div>
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
.float-toggle { margin-left: auto; color: #8C8C8C; font-size: 11px; }
.float-panel:not(.collapsed) .float-toggle { margin-left: 0; }
.float-body { padding: 8px 14px 12px; max-height: 360px; overflow-y: auto; }
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
.step-icon { font-size: 10px; }
.task-actions { display: flex; justify-content: flex-end; gap: 4px; }
.empty-hint { font-size: 12px; color: #8C8C8C; text-align: center; padding: 12px 0; }
</style>
