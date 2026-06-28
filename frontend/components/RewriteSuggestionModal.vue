<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useBookApi } from '~/composables/useBookApi'

const props = defineProps<{
  visible: boolean
  chapterId: number | null
  suggestions: string[]
  chapterContent: string
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'rewriteComplete', content: string): void
}>()

const api = useBookApi()
const msg = useMessage()

const instructions = ref('')
const lengthMode = ref<'similar' | 'expand' | 'condense'>('similar')
const rewriting = ref(false)

// 打开时把建议预填到指令框
watch(() => props.visible, (v) => {
  if (v && props.suggestions.length) {
    instructions.value = props.suggestions
      .map((s, i) => `${i + 1}. ${s}`)
      .join('\n')
    lengthMode.value = 'similar'
  }
})

const canSubmit = computed(() => instructions.value.trim().length > 0 && !rewriting.value)

const lengthOptions = [
  { label: '保持相似长度', value: 'similar' },
  { label: '扩写（加长）', value: 'expand' },
  { label: '精简（缩短）', value: 'condense' },
]

function onClose() {
  if (!rewriting.value) {
    emit('update:visible', false)
  }
}

async function onSubmit() {
  if (!props.chapterId || !instructions.value.trim()) return

  rewriting.value = true
  try {
    const r = await api.regenerateChapter(props.chapterId, {
      modification_instructions: instructions.value.trim(),
      focus_areas: [],
      preserve_elements: [],
      length_mode: lengthMode.value,
      target_word_count: null,
      version_note: '根据分析建议重写',
    })
    if (r?.regenerated_content) {
      emit('rewriteComplete', r.regenerated_content)
      emit('update:visible', false)
    } else {
      msg.warning('重写未返回内容')
    }
  } catch (e: any) {
    msg.error('重写失败：' + formatError(e))
  } finally {
    rewriting.value = false
  }
}
</script>

<template>
  <a-modal
    :open="visible"
    title="✏️ 根据建议改写"
    width="680px"
    :footer="null"
    :maskClosable="!rewriting"
    @cancel="onClose"
  >
    <div class="rewrite-modal-body">
      <!-- AI 建议速览 -->
      <div v-if="suggestions.length" class="suggestions-ref">
        <div class="section-label">📋 AI 分析建议（参考）</div>
        <div class="suggestion-chips">
          <span v-for="(s, i) in suggestions" :key="i" class="suggestion-chip">
            <span class="chip-num">{{ i + 1 }}</span>
            {{ s }}
          </span>
        </div>
      </div>

      <!-- 改写指令编辑 -->
      <div class="instructions-section">
        <div class="section-label">📝 改写方向（可自由编辑）</div>
        <a-textarea
          v-model:value="instructions"
          placeholder="输入具体的改写方向，AI 将根据这些指令重写章节内容..."
          :rows="6"
          :auto-size="{ minRows: 4, maxRows: 10 }"
          class="instructions-input"
        />
      </div>

      <!-- 长度模式 -->
      <div class="options-row">
        <span class="section-label" style="margin:0">📏 长度</span>
        <a-radio-group v-model:value="lengthMode" size="small">
          <a-radio-button v-for="opt in lengthOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </a-radio-button>
        </a-radio-group>
      </div>

      <!-- 底部按钮 -->
      <div class="modal-footer">
        <a-button @click="onClose" :disabled="rewriting">取消</a-button>
        <a-button
          type="primary"
          :loading="rewriting"
          :disabled="!canSubmit"
          @click="onSubmit"
        >
          {{ rewriting ? '正在改写...' : '🚀 开始改写' }}
        </a-button>
      </div>
    </div>
  </a-modal>
</template>

<style scoped>
.rewrite-modal-body {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.section-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary, #666);
  margin-bottom: 8px;
}
.suggestions-ref {
  background: var(--bg-elevated, #f7f8fa);
  border-radius: 8px;
  padding: 14px 16px;
}
.suggestion-chips {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.suggestion-chip {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-primary, #333);
  padding: 6px 10px;
  background: var(--bg-base, #fff);
  border-radius: 6px;
  border: 1px solid var(--border-base, #e8e8e8);
}
.chip-num {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--primary-color, #1677ff);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 1px;
}
.instructions-input {
  width: 100%;
}
.options-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--border-base, #f0f0f0);
}
</style>
