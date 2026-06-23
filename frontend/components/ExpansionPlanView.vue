<script setup lang="ts">
// 章节规划只读详情（对标 MuMu showExpansionPlanModal）
const props = defineProps<{
  open: boolean
  chapterNumber: number
  chapterTitle?: string
  plan?: Record<string, any> | null
  chapterSummary?: string
}>()

const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

const planData = computed(() => props.plan || {})
const summary = computed(() => planData.value.summary ?? props.chapterSummary ?? '')
const keyEvents = computed<string[]>(() => Array.isArray(planData.value.key_events) ? planData.value.key_events : [])
const characterFocus = computed<string[]>(() => Array.isArray(planData.value.character_focus) ? planData.value.character_focus : [])

function close() {
  emit('update:open', false)
}
</script>

<template>
  <a-modal
    :open="open"
    :title="`📋 章节规划 · 第${chapterNumber}章`"
    :width="640"
    centered
    :footer="null"
    @cancel="close"
  >
    <div v-if="chapterTitle" class="view-subtitle">章节：{{ chapterTitle }}</div>

    <a-descriptions :column="2" size="small" bordered class="view-desc">
      <a-descriptions-item label="情感基调" :span="1">
        {{ planData.emotional_tone || '—' }}
      </a-descriptions-item>
      <a-descriptions-item label="冲突类型" :span="1">
        {{ planData.conflict_type || '—' }}
      </a-descriptions-item>
      <a-descriptions-item label="预估字数" :span="2">
        {{ planData.estimated_words ? planData.estimated_words + ' 字' : '—' }}
      </a-descriptions-item>
    </a-descriptions>

    <div v-if="summary" class="view-block">
      <div class="view-block-title">情节概要</div>
      <div class="view-block-text">{{ summary }}</div>
    </div>

    <div v-if="keyEvents.length" class="view-block">
      <div class="view-block-title">关键事件</div>
      <div class="tag-row">
        <a-tag v-for="(ev, i) in keyEvents" :key="i" color="blue">{{ ev }}</a-tag>
      </div>
    </div>

    <div v-if="characterFocus.length" class="view-block">
      <div class="view-block-title">涉及角色</div>
      <div class="tag-row">
        <a-tag v-for="(c, i) in characterFocus" :key="i" color="orange">{{ c }}</a-tag>
      </div>
    </div>

    <div v-if="planData.narrative_goal" class="view-block">
      <div class="view-block-title">叙事目标</div>
      <div class="view-block-text">{{ planData.narrative_goal }}</div>
    </div>

    <a-empty v-if="!summary && !keyEvents.length && !characterFocus.length && !planData.narrative_goal"
      description="该章节暂无规划" style="margin: 40px 0" />
  </a-modal>
</template>

<style scoped>
.view-subtitle { font-size: 13px; color: #8C8C8C; margin-bottom: 14px; }
.view-desc { margin-bottom: 16px; }
.view-block { margin-bottom: 16px; }
.view-block-title { font-size: 13px; font-weight: 600; color: #4D8088; margin-bottom: 8px; }
.view-block-text { font-size: 14px; color: #595959; line-height: 1.7; white-space: pre-wrap; }
.tag-row { display: flex; flex-wrap: wrap; gap: 6px; }
</style>
