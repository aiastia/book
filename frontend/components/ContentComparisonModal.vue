<script setup lang="ts">
import { computed, ref } from 'vue'
import { diffWords } from 'diff'

const props = defineProps<{
  visible: boolean
  title?: string
  originalContent: string
  newContent: string
  showActions?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'apply'): void
  (e: 'discard'): void
}>()

const msg = useMessage()
const viewMode = ref<'split' | 'unified'>('split')
const applying = ref(false)

const diffParts = computed(() => {
  if (!props.originalContent || !props.newContent) return []
  return diffWords(props.originalContent, props.newContent)
})

const origCount = computed(() => props.originalContent?.length || 0)
const newCount = computed(() => props.newContent?.length || 0)
const diffCount = computed(() => newCount.value - origCount.value)
const diffPercent = computed(() => {
  if (!origCount.value) return '0'
  return ((diffCount.value / origCount.value) * 100).toFixed(1)
})

function onClose() {
  emit('update:visible', false)
}
function onApply() {
  applying.value = true
  emit('apply')
  applying.value = false
  emit('update:visible', false)
}
function onDiscard() {
  emit('discard')
  emit('update:visible', false)
}
</script>

<template>
  <a-modal
    :open="visible"
    :title="title || '内容对比'"
    width="95%"
    centered
    :style="{ maxWidth: '1400px' }"
    :footer="null"
    @cancel="onClose"
  >
    <!-- 统计栏 -->
    <div class="compare-stats">
      <div class="stat-item">
        <span class="stat-label">原内容</span>
        <span class="stat-value">{{ origCount.toLocaleString() }} 字</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">新内容</span>
        <span class="stat-value">{{ newCount.toLocaleString() }} 字</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">变化</span>
        <span class="stat-value" :class="{ 'stat-up': diffCount > 0, 'stat-down': diffCount < 0 }">
          {{ diffCount > 0 ? '+' : '' }}{{ diffCount }} 字
        </span>
      </div>
      <div class="stat-item">
        <span class="stat-label">变化率</span>
        <span class="stat-value" :class="{ 'stat-warn': Math.abs(parseFloat(diffPercent)) >= 10 }">
          {{ diffCount > 0 ? '+' : '' }}{{ diffPercent }}%
        </span>
      </div>
      <div class="stat-item" style="margin-left:auto">
        <a-radio-group v-model:value="viewMode" size="small">
          <a-radio-button value="split">左右对比</a-radio-button>
          <a-radio-button value="unified">合并视图</a-radio-button>
        </a-radio-group>
      </div>
    </div>

    <!-- Split 视图 -->
    <div v-if="viewMode === 'split'" class="diff-split">
      <div class="diff-side diff-side-left">
        <div class="diff-side-title">原内容</div>
        <div class="diff-side-content">
          <template v-for="(part, idx) in diffParts" :key="idx">
            <span v-if="part.removed" class="diff-removed">{{ part.value }}</span>
            <span v-else-if="!part.added">{{ part.value }}</span>
          </template>
        </div>
      </div>
      <div class="diff-divider" />
      <div class="diff-side diff-side-right">
        <div class="diff-side-title">新内容</div>
        <div class="diff-side-content">
          <template v-for="(part, idx) in diffParts" :key="idx">
            <span v-if="part.added" class="diff-added">{{ part.value }}</span>
            <span v-else-if="!part.removed">{{ part.value }}</span>
          </template>
        </div>
      </div>
    </div>

    <!-- Unified 视图 -->
    <div v-else class="diff-unified">
      <template v-for="(part, idx) in diffParts" :key="idx">
        <span v-if="part.added" class="diff-added">{{ part.value }}</span>
        <span v-else-if="part.removed" class="diff-removed">{{ part.value }}</span>
        <span v-else>{{ part.value }}</span>
      </template>
    </div>

    <!-- 底部按钮 -->
    <div v-if="showActions" class="compare-footer">
      <a-button danger @click="onDiscard">放弃新内容</a-button>
      <a-button type="primary" :loading="applying" @click="onApply">应用新内容</a-button>
    </div>
  </a-modal>
</template>

<style scoped>
.compare-stats {
  display: flex; gap: 24px; align-items: center;
  padding: 12px 16px; background: #f7f6f2; border-radius: 8px;
  margin-bottom: 12px; flex-wrap: wrap;
}
.stat-item { display: flex; flex-direction: column; gap: 2px; }
.stat-label { font-size: 11px; color: #8c8c8c; }
.stat-value { font-size: 16px; font-weight: 600; color: #333; }
.stat-up { color: #52c41a; }
.stat-down { color: #ff4d4f; }
.stat-warn { color: #faad14; }

.diff-split {
  display: flex; gap: 0;
  border: 1px solid #ebe7df; border-radius: 8px; overflow: hidden;
  max-height: 55vh;
}
.diff-side { flex: 1; overflow-y: auto; }
.diff-side-left { background: #fff5f5; }
.diff-side-right { background: #f0fff4; }
.diff-side-title {
  font-size: 12px; font-weight: 600; padding: 6px 12px;
  border-bottom: 1px solid #ebe7df; color: #595959;
  position: sticky; top: 0; background: #faf9f6; z-index: 1;
}
.diff-side-content {
  padding: 10px 14px; font-size: 13px; line-height: 1.9;
  white-space: pre-wrap; word-break: break-all;
}
.diff-divider { width: 1px; background: #ebe7df; flex-shrink: 0; }

.diff-unified {
  max-height: 55vh; overflow-y: auto;
  border: 1px solid #ebe7df; border-radius: 8px;
  padding: 12px 16px; font-size: 13px; line-height: 1.9;
  white-space: pre-wrap; word-break: break-all; background: #fff;
}

.diff-added { background: #d4edda; color: #155724; padding: 0 2px; border-radius: 2px; }
.diff-removed { background: #f8d7da; color: #721c24; text-decoration: line-through; padding: 0 2px; border-radius: 2px; }

.compare-footer {
  display: flex; gap: 12px; justify-content: flex-end;
  margin-top: 16px; padding-top: 12px; border-top: 1px solid #ebe7df;
}
</style>
