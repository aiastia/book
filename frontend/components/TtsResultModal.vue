<template>
  <a-modal
    :open="open"
    title="🔊 语音合成 SSML"
    width="80%"
    :footer="null"
    @update:open="$emit('update:open', $event)"
  >
    <!-- 统计信息 -->
    <div v-if="result?.stats" class="tts-stats">
      <a-tag color="blue">{{ result.stats.lines }} 句</a-tag>
      <a-tag color="purple">{{ result.stats.scenes }} 个场景</a-tag>
      <a-tag color="green">{{ result.stats.chars }} 字</a-tag>
      <a-tag color="orange">{{ result.stats.ssml_parts }} 段 SSML</a-tag>
    </div>

    <!-- 片段选择(如果多个) -->
    <div v-if="ssmlParts.length > 1" class="tts-tabs">
      <a-radio-group v-model:value="activePart" size="small">
        <a-radio-button v-for="(_, i) in ssmlParts" :key="i" :value="i">片段 {{ i + 1 }}</a-radio-button>
      </a-radio-group>
    </div>

    <!-- SSML 预览 -->
    <pre class="tts-code">{{ currentSsml }}</pre>

    <!-- 操作按钮 -->
    <div class="tts-actions">
      <a-button @click="copySsml">📋 复制 SSML</a-button>
      <a-button type="primary" @click="downloadSsml">💾 下载 .xml</a-button>
      <a-button v-if="ssmlParts.length > 1" @click="downloadAll">💾 下载全部 ({{ ssmlParts.length }} 段)</a-button>
    </div>

    <!-- Director JSON 折叠(调试用) -->
    <a-collapse v-if="result?.director_json" :bordered="false" class="tts-collapse">
      <a-collapse-panel key="director" header="📖 Director 分析结果(调试)">
        <pre class="tts-director">{{ JSON.stringify(result.director_json, null, 2) }}</pre>
      </a-collapse-panel>
    </a-collapse>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

interface TtsResult {
  success: boolean
  ssml_parts: string[]
  director_json?: any[]
  stats?: { lines: number; scenes: number; chars: number; ssml_parts: number }
  error?: string
}

const props = defineProps<{
  open: boolean
  result: TtsResult | null
}>()

defineEmits(['update:open'])

const activePart = ref(0)

const ssmlParts = computed(() => props.result?.ssml_parts || [])
const currentSsml = computed(() => ssmlParts.value[activePart.value] || '')

// 弹窗打开时重置选中
watch(() => props.open, (v) => { if (v) activePart.value = 0 })

async function copySsml() {
  try {
    await navigator.clipboard.writeText(currentSsml.value)
  } catch {
    // fallback
    const ta = document.createElement('textarea')
    ta.value = currentSsml.value
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
  }
  const { success } = useMessage()
  success('已复制到剪贴板')
}

function downloadSsml() {
  download(currentSsml.value, `ssml_part${activePart.value + 1}.xml`)
}

function downloadAll() {
  ssmlParts.value.forEach((s, i) => download(s, `ssml_part${i + 1}.xml`))
}

function download(content: string, filename: string) {
  const blob = new Blob([content], { type: 'application/xml;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.tts-stats {
  margin-bottom: 12px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.tts-tabs {
  margin-bottom: 12px;
}
.tts-code {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 16px;
  border-radius: 6px;
  max-height: 400px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
}
.tts-actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}
.tts-collapse {
  margin-top: 16px;
}
.tts-director {
  background: #f5f5f5;
  padding: 12px;
  border-radius: 4px;
  max-height: 300px;
  overflow: auto;
  font-size: 11px;
  white-space: pre-wrap;
}
</style>
