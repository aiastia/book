<script setup lang="ts">
// 章节规划编辑器（对标 MuMuAINovel ExpansionPlanEditor）
// 编辑 expansion_plan：情节概要 / 关键事件 / 涉及角色 / 情感基调 / 冲突类型 / 叙事目标 / 预估字数
// 后端 expansion_plan 字段已存在（Chapter.expansion_plan JSON），保存走 updateChapter。
import { apiGet } from '~/composables/useApi'
import { useProject } from '~/composables/useProject'
import { useProjectApi } from '~/composables/useProjectApi'

const props = defineProps<{
  open: boolean
  chapterId: number
  chapterNumber: number
  chapterTitle?: string
  planData?: Record<string, any> | null
  chapterSummary?: string
}>()

const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'saved', plan: Record<string, any>): void
}>()

const { currentProjectId } = useProject()
const api = useProjectApi()
const msg = useMessage()

// 表单字段
const summary = ref('')
const emotionalTone = ref('紧张激烈')
const conflictType = ref('人物冲突')
const narrativeGoal = ref('')
const estimatedWords = ref(4000)

// 关键事件（标签）
const keyEvents = ref<string[]>([])
const keyEventInput = ref('')

// 涉及角色
const availableCharacters = ref<any[]>([])
const characterFocus = ref<string[]>([])
const loadingCharacters = ref(false)

const saving = ref(false)

// 冲突类型候选项
const conflictTypeOptions = ['人物冲突', '环境冲突', '内心冲突', '理念冲突', '势力冲突', '命运冲突']
const emotionalToneOptions = ['紧张激烈', '温馨治愈', '悲壮压抑', '轻松幽默', '悬疑烧脑', '热血激昂', '哀婉凄美']

// 加载项目角色
async function loadCharacters() {
  loadingCharacters.value = true
  try {
    const list = await apiGet<any[]>(`/api/projects/${currentProjectId.value}/characters`)
    availableCharacters.value = (list || []).map((c: any) => ({
      name: c.name,
      role: c.role || '',
      label: c.role ? `${c.name}（${c.role}）` : c.name,
    }))
  } catch (e: any) {
    console.warn('加载角色失败', e)
  } finally {
    loadingCharacters.value = false
  }
}

// 当弹窗打开 / planData 变化时回填
watch(
  () => [props.open, props.planData, props.chapterSummary],
  ([isOpen]) => {
    if (!isOpen) return
    const plan = props.planData || {}
    summary.value = plan.summary ?? props.chapterSummary ?? ''
    keyEvents.value = Array.isArray(plan.key_events) ? [...plan.key_events] : []
    characterFocus.value = Array.isArray(plan.character_focus) ? [...plan.character_focus] : []
    emotionalTone.value = plan.emotional_tone || '紧张激烈'
    conflictType.value = plan.conflict_type || '人物冲突'
    narrativeGoal.value = plan.narrative_goal || ''
    estimatedWords.value = plan.estimated_words || 4000
    keyEventInput.value = ''
  },
  { immediate: true }
)

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen && currentProjectId.value) loadCharacters()
  }
)

function addKeyEvent() {
  const v = keyEventInput.value.trim()
  if (v && !keyEvents.value.includes(v)) {
    keyEvents.value.push(v)
    keyEventInput.value = ''
  }
}
function removeKeyEvent(idx: number) {
  keyEvents.value.splice(idx, 1)
}

function close() {
  emit('update:open', false)
}

async function onSave() {
  if (keyEvents.value.length === 0) {
    msg.warning('请至少添加一个关键事件')
    return
  }
  if (characterFocus.value.length === 0) {
    msg.warning('请至少选择一个涉及角色')
    return
  }
  saving.value = true
  try {
    const plan = {
      summary: summary.value,
      key_events: keyEvents.value,
      character_focus: characterFocus.value,
      emotional_tone: emotionalTone.value,
      conflict_type: conflictType.value,
      narrative_goal: narrativeGoal.value,
      estimated_words: estimatedWords.value,
    }
    await api.updateChapter(props.chapterId, { expansion_plan: plan })
    msg.success('规划保存成功')
    emit('saved', plan)
    close()
  } catch (e: any) {
    msg.error('保存失败：' + formatError(e))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <a-modal
    :open="open"
    :title="`📋 编辑章节规划 · 第${chapterNumber}章`"
    :width="680"
    centered
    :destroy-on-close="true"
    :ok-text="saving ? '保存中…' : '保存'"
    :confirm-loading="saving"
    @ok="onSave"
    @cancel="close"
  >
    <div v-if="chapterTitle" class="plan-subtitle">章节：{{ chapterTitle }}</div>

    <a-form layout="vertical" class="plan-form">
      <!-- 情节概要 -->
      <a-form-item label="情节概要" tooltip="简要描述本章的主要情节和故事走向">
        <a-textarea
          v-model:value="summary"
          :rows="4"
          placeholder="例如：主角得知身世真相，与反派在悬崖展开最终对决……"
        />
      </a-form-item>

      <!-- 关键事件 -->
      <a-form-item label="关键事件">
        <div class="tag-row">
          <a-tag
            v-for="(ev, i) in keyEvents"
            :key="i"
            closable
            color="blue"
            @close="removeKeyEvent(i)"
          >
            {{ ev }}
          </a-tag>
        </div>
        <a-input-search
          v-model:value="keyEventInput"
          placeholder="输入关键事件后回车/点添加"
          enter-button="添加"
          size="small"
          @search="addKeyEvent"
        />
      </a-form-item>

      <!-- 涉及角色 -->
      <a-form-item label="涉及角色">
        <a-select
          v-model:value="characterFocus"
          mode="multiple"
          :loading="loadingCharacters"
          placeholder="选择本章主要角色"
          :options="availableCharacters.map(c => ({ value: c.name, label: c.label }))"
          :field-names="{ value: 'value', label: 'label' }"
          option-filter-prop="label"
        />
      </a-form-item>

      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="情感基调">
            <a-select v-model:value="emotionalTone" :options="emotionalToneOptions.map(o => ({ value: o, label: o }))" />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="冲突类型">
            <a-select v-model:value="conflictType" :options="conflictTypeOptions.map(o => ({ value: o, label: o }))" />
          </a-form-item>
        </a-col>
      </a-row>

      <!-- 叙事目标 -->
      <a-form-item label="叙事目标" tooltip="本章在整本书结构中要达成的目的">
        <a-textarea v-model:value="narrativeGoal" :rows="2" placeholder="例如：引出最终 BOSS、回收身世伏笔、完成主角成长弧线" />
      </a-form-item>

      <!-- 预估字数 -->
      <a-form-item label="预估字数">
        <a-input-number v-model:value="estimatedWords" :min="500" :max="10000" :step="100" style="width: 160px" />
        <span class="word-hint">字</span>
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<style scoped>
.plan-subtitle {
  font-size: 13px;
  color: #8C8C8C;
  margin-bottom: 12px;
}
.plan-form { max-height: 60vh; overflow-y: auto; padding-right: 4px; }
.tag-row { margin-bottom: 8px; min-height: 24px; }
.tag-row :deep(.ant-tag) { margin-bottom: 4px; }
.word-hint { margin-left: 8px; color: #8C8C8C; font-size: 13px; }
</style>
