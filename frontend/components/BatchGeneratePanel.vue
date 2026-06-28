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

// 可选起始章（空章节 + 下一章号）
const emptyChapters = computed(() => {
  return (props.chapters || []).filter((c: any) => !c.word_count || c.status === 'draft')
})
// 默认起始章 = 第一个空章节，无空章节时 = 最后一章+1（接续生成）
const defaultStartChapter = computed(() => {
  if (emptyChapters.value.length) return emptyChapters.value[0].chapter_number
  const list = props.chapters || []
  return list.length ? list[list.length - 1].chapter_number + 1 : 1
})

// 从起始章开始，可用的空章节数量（无空章节时算接续生成，无上限限制）
const availableCount = computed(() => {
  const start = startChapterNumber.value || 1
  const empties = emptyChapters.value.filter((c: any) => c.chapter_number >= start).length
  if (empties > 0) return empties
  // 无空章节 = 接续生成，数量不受已有章节限制
  return 40
})
// 实际生成数量
const actualCount = computed(() => {
  return Math.min(count.value, availableCount.value || 1)
})

// 项目默认叙事视角（用于 placeholder / 「按小说设定」展示）
const projectDefaultPov = ref('第三人称')

// 当前任务状态（仅用于展示已完成的结果，进行中由悬浮栏跟踪）
const currentTask = ref<any>(null)

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
  if (remoteModels.value.length && defaultModelName.value) return
  loadingModels.value = true
  try {
    const r = await api.fetchDefaultRemoteModels()
    remoteModels.value = r.models || []
    defaultModelName.value = r.default_model || ''
  } catch (e: any) {
    // 远程拉取失败，从本地配置取默认模型名
    try {
      const models = await api.listAiModels()
      const def = models.find((m: any) => m.is_default) || models[0]
      if (def?.model) defaultModelName.value = def.model
    } catch {}
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
    if (t && ['completed', 'failed', 'cancelled'].includes(t.status)) {
      currentTask.value = t  // 只记录已完成的状态用于展示结果
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
    trackTask({ id: r.task_id, task_type: 'chapter_batch', title: `批量生成 ${actualCount.value} 章` })
    open.value = false  // 关闭弹窗，进度由悬浮栏显示
    emit('done')
  } catch (e: any) {
    msg.error('提交失败：' + formatError(e))
  } finally {
    submitting.value = false
  }
}

onUnmounted(() => {})

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
      <!-- 任务完成/失败提示（进行中由悬浮栏显示，不在此重复） -->
      <a-alert
        v-if="currentTask && ['completed', 'failed', 'cancelled'].includes(currentTask.status)"
        :type="currentTask.status === 'completed' ? 'success' : currentTask.status === 'failed' ? 'error' : 'warning'"
        show-icon
        style="margin-bottom: 16px"
        closable
        @close="currentTask = null"
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
            <a-select v-model:value="startChapterNumber" style="width:100%" :placeholder="`第${defaultStartChapter}章`">
              <a-select-option v-if="!emptyChapters.length" :value="defaultStartChapter">
                第{{ defaultStartChapter }}章（接续生成）
              </a-select-option>
              <a-select-option v-for="c in emptyChapters" :key="c.id" :value="c.chapter_number">
                第{{ c.chapter_number }}章{{ c.title ? '：' + c.title : '（空）' }}
              </a-select-option>
            </a-select>
            <div class="field-hint">
              {{ emptyChapters.length ? `可选 ${emptyChapters.length} 个空章节` : '无空章节，将接续生成新章节' }}
            </div>
          </div>
          <div class="form-col">
            <label class="form-label">生成数量：{{ count }} 章</label>
            <a-slider v-model:value="count" :min="1" :max="40" :marks="{ 1: '1', 5: '5', 10: '10', 20: '20', 40: '40' }" />
            <div class="field-hint">
              <template v-if="actualCount < count">可用空章节 {{ availableCount }} 章，实际将生成 {{ actualCount }} 章</template>
              <template v-else>将生成第 {{ startChapterNumber }} ~ {{ (startChapterNumber || 1) + actualCount - 1 }} 章</template>
            </div>
          </div>
        </div>

        <!-- 风格 + 字数 -->
        <div class="form-row-2">
          <div class="form-col">
            <label class="form-label">写作风格</label>
            <a-select v-model:value="styleId" style="width:100%" :placeholder="projectDefaultStyleName ? `默认（${projectDefaultStyleName}）` : '项目默认风格'" allow-clear show-search option-filter-prop="label">
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
              <a-select-option value="">{{ defaultModelName ? `使用默认（${defaultModelName}）` : '使用默认模型' }}</a-select-option>
              <a-select-option v-for="m in remoteModels" :key="m.id" :value="m.id" :label="m.id">{{ m.id }}</a-select-option>
            </a-select>
          </div>
          <div class="form-col">
            <label class="form-label">叙事视角</label>
            <a-select v-model:value="narrativePerspective" style="width:100%" :placeholder="`按小说设定（${projectDefaultPov}）`" allow-clear>
              <a-select-option value="">{{ `按小说设定（${projectDefaultPov}）` }}</a-select-option>
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
