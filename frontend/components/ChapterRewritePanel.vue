<script setup lang="ts">
// 章节重写面板（#11 重写历史 + #13 扩写缩写/局部重写）
// 对标 MuMuAINovel Chapters 重写功能
import { API } from '~/composables/api'

const props = defineProps<{
  chapterId: number | null
  chapterContent: string
}>()
const emit = defineEmits<{ (e: 'applied'): void; (e: 'regenerated', content: string): void }>()

const msg = useMessage()

const open = ref(false)
const mode = ref<'full' | 'partial' | 'history'>('full')

// 全章重写表单
const rewriteForm = reactive({
  modification_instructions: '',
  focus_areas: [] as string[],
  preserve_elements: [] as string[],
  length_mode: 'similar',
  target_word_count: null as number | null,
  version_note: '',
})
const rewriting = ref(false)
const rewriteResult = ref<any>(null)

// 局部重写
const selection = ref('')
const partialInstructions = ref('')
const partialLengthMode = ref('similar')
const partialResult = ref<any>(null)
const partialLoading = ref(false)
const textareaRef = ref<any>(null)

// 历史
const history = ref<any[]>([])
const historyDetail = ref<any>(null)
const loadingHistory = ref(false)
const compareOpen = computed(() => !!historyDetail.value)

const focusOptions = [
  { label: '节奏', value: 'pacing' },
  { label: '情感', value: 'emotion' },
  { label: '描写', value: 'description' },
  { label: '对话', value: 'dialogue' },
  { label: '冲突', value: 'conflict' },
]
const lengthOptions = [
  { label: '保持相似', value: 'similar' },
  { label: '扩写（加长）', value: 'expand' },
  { label: '精简（缩短）', value: 'condense' },
  { label: '自定义字数', value: 'custom' },
]

function openPanel() {
  if (!props.chapterId) {
    msg.warning('请先选择章节')
    return
  }
  resetForms()
  open.value = true
  loadHistory()
}

function resetForms() {
  rewriteForm.modification_instructions = ''
  rewriteForm.focus_areas = []
  rewriteForm.preserve_elements = []
  rewriteForm.length_mode = 'similar'
  rewriteForm.target_word_count = null
  rewriteForm.version_note = ''
  rewriteResult.value = null
  selection.value = ''
  partialInstructions.value = ''
  partialResult.value = null
  historyDetail.value = null
}

// 全章重写
async function onRewrite() {
  if (!props.chapterId) return
  rewriting.value = true
  rewriteResult.value = null
  try {
    const r = await API.chapter.regenerate(props.chapterId, { ...rewriteForm })
    rewriteResult.value = r
    msg.success('重写完成')
    await loadHistory()
    // emit regenerated 事件，让父组件打开对比弹窗
    if (r?.regenerated_content) {
      emit('regenerated', r.regenerated_content)
    }
  } catch (e: any) {
    msg.error('重写失败：' + formatError(e))
  } finally {
    rewriting.value = false
  }
}

async function onApplyRewrite() {
  if (!rewriteResult.value || !props.chapterId) return
  if (!await msg.confirm('确认用重写内容覆盖原章节？')) return
  try {
    await API.chapter.applyRegenTask(props.chapterId, rewriteResult.value.id)
    msg.success('已应用')
    open.value = false
    emit('applied')
  } catch (e: any) {
    msg.error('应用失败：' + formatError(e))
  }
}

// 局部重写 - 从 textarea 获取选中文本
function getSelection() {
  const ta = textareaRef.value?.$el?.querySelector('textarea') || textareaRef.value?.$el
  if (!ta || typeof ta.selectionStart === 'undefined') {
    msg.warning('请在文本框中选中要重写的片段')
    return
  }
  const start = ta.selectionStart
  const end = ta.selectionEnd
  if (end - start < 10) {
    msg.warning('请选中至少 10 个字符的片段')
    return
  }
  selection.value = props.chapterContent.substring(start, end)
  partialResult.value = { start_position: start, end_position: end }
}

async function onPartialRewrite() {
  if (!selection.value || !props.chapterId) {
    msg.warning('请先选中文本片段')
    return
  }
  partialLoading.value = true
  try {
    const r = await API.chapter.partialRegenerate(props.chapterId, {
      selected_text: selection.value,
      start_position: partialResult.value?.start_position || 0,
      end_position: partialResult.value?.end_position || 0,
      instructions: partialInstructions.value,
      length_mode: partialLengthMode.value,
    })
    partialResult.value = r
  } catch (e: any) {
    msg.error('局部重写失败：' + formatError(e))
  } finally {
    partialLoading.value = false
  }
}

async function onApplyPartial() {
  if (!partialResult.value || !props.chapterId) return
  if (!await msg.confirm('确认替换选中的片段？')) return
  try {
    await API.chapter.applyPartialRegen(props.chapterId, {
      new_text: partialResult.value.regenerated_text,
      start_position: partialResult.value.start_position,
      end_position: partialResult.value.end_position,
    })
    msg.success('已替换')
    open.value = false
    emit('applied')
  } catch (e: any) {
    msg.error('应用失败：' + formatError(e))
  }
}

// 历史
async function loadHistory() {
  if (!props.chapterId) return
  loadingHistory.value = true
  try {
    history.value = await API.chapter.getRegenTasks(props.chapterId)
  } catch (e: any) {
    msg.error('加载历史失败：' + formatError(e))
  } finally {
    loadingHistory.value = false
  }
}
async function viewHistory(task: any) {
  if (!props.chapterId) return
  try {
    historyDetail.value = await API.chapter.getRegenTaskDetail(props.chapterId, task.id)
  } catch (e: any) {
    msg.error('加载详情失败：' + formatError(e))
  }
}
async function applyHistory(task: any) {
  if (!props.chapterId) return
  if (!await msg.confirm(`确认应用「${task.version_note || '版本 ' + task.version_number}」覆盖当前章节？`)) return
  try {
    await API.chapter.applyRegenTask(props.chapterId, task.id)
    msg.success('已应用')
    open.value = false
    emit('applied')
  } catch (e: any) {
    msg.error('应用失败：' + formatError(e))
  }
}

// 文本对比工具（简单行级 diff）
const diffHtml = computed(() => {
  if (!historyDetail.value) return ''
  const orig = (historyDetail.value.original_content || '').split('\n')
  const regen = (historyDetail.value.regenerated_content || '').split('\n')
  const d = diffLines(orig, regen)
  return d
})
function diffLines(a: string[], b: string[]) {
  const result: { type: 'same' | 'add' | 'del'; text: string }[] = []
  let i = 0, j = 0
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      result.push({ type: 'same', text: a[i] }); i++; j++
    } else if (i < a.length && !b.includes(a[i])) {
      result.push({ type: 'del', text: a[i] }); i++
    } else if (j < b.length && !a.includes(b[j])) {
      result.push({ type: 'add', text: b[j] }); j++
    } else {
      if (i < a.length) { result.push({ type: 'del', text: a[i] }); i++ }
      if (j < b.length) { result.push({ type: 'add', text: b[j] }); j++ }
    }
  }
  return result.map(r => {
    if (r.type === 'add') return `<div class="diff-add">+ ${escapeHtml(r.text)}</div>`
    if (r.type === 'del') return `<div class="diff-del">- ${escapeHtml(r.text)}</div>`
    return `<div class="diff-same">  ${escapeHtml(r.text)}</div>`
  }).join('')
}
function escapeHtml(s: string) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}
</script>

<template>
  <span>
    <a-button @click="openPanel">✏️ 重写/润色</a-button>

    <a-modal v-model:open="open" title="章节重写" width="820px" :footer="null">
      <a-tabs v-model:activeKey="mode">
        <!-- 全章重写 -->
        <a-tab-pane key="full" tab="全章重写">
          <a-form layout="vertical">
            <a-form-item label="修改指令">
              <a-textarea v-model:value="rewriteForm.modification_instructions" :rows="3"
                placeholder="如：加强主角的心理描写、增加环境氛围渲染、让对话更自然..." />
            </a-form-item>
            <a-form-item label="聚焦领域（可多选）">
              <a-checkbox-group v-model:value="rewriteForm.focus_areas">
                <a-checkbox v-for="f in focusOptions" :key="f.value" :value="f.value">{{ f.label }}</a-checkbox>
              </a-checkbox-group>
            </a-form-item>
            <a-form-item label="长度模式">
              <a-radio-group v-model:value="rewriteForm.length_mode">
                <a-radio-button v-for="l in lengthOptions" :key="l.value" :value="l.value">{{ l.label }}</a-radio-button>
              </a-radio-group>
              <a-input-number v-if="rewriteForm.length_mode === 'custom'" v-model:value="rewriteForm.target_word_count"
                :min="500" :step="500" addon-before="目标字数" style="margin-left:12px;width:200px" />
            </a-form-item>
            <a-form-item label="版本备注">
              <a-input v-model:value="rewriteForm.version_note" placeholder="如：加强心理描写版" />
            </a-form-item>
          </a-form>
          <div class="action-bar">
            <a-button type="primary" :loading="rewriting" @click="onRewrite">
              {{ rewriting ? '重写中（可能需1-2分钟）…' : '开始重写' }}
            </a-button>
          </div>
          <!-- 重写结果 -->
          <div v-if="rewriteResult" class="result-box">
            <div class="result-meta">
              <a-tag color="success">版本 {{ rewriteResult.version_number }}</a-tag>
              <span class="wc-info">原文 {{ rewriteResult.original_word_count }} 字 → 重写 {{ rewriteResult.regenerated_word_count }} 字</span>
              <a-button type="primary" size="small" @click="onApplyRewrite">应用此版本</a-button>
            </div>
          </div>
        </a-tab-pane>

        <!-- 局部重写 -->
        <a-tab-pane key="partial" tab="局部重写">
          <a-alert message="先在下方文本框选中要重写的片段，再点击「获取选中」" type="info" show-icon style="margin-bottom:12px" />
          <a-textarea ref="textareaRef" :value="chapterContent" :rows="6" readonly style="margin-bottom:10px" />
          <div class="partial-bar">
            <a-button @click="getSelection">📋 获取选中</a-button>
            <a-radio-group v-model:value="partialLengthMode" size="small">
              <a-radio-button value="similar">相似</a-radio-button>
              <a-radio-button value="expand">扩写</a-radio-button>
              <a-radio-button value="condense">精简</a-radio-button>
            </a-radio-group>
          </div>
          <div v-if="selection" class="selection-preview">
            <div class="preview-label">选中片段（{{ selection.length }}字）：</div>
            <div class="preview-text">{{ selection.substring(0, 200) }}{{ selection.length > 200 ? '…' : '' }}</div>
          </div>
          <a-form-item label="重写要求（可选）" style="margin-top:10px">
            <a-input v-model:value="partialInstructions" placeholder="如：更紧张、增加动作细节" />
          </a-form-item>
          <div class="action-bar">
            <a-button type="primary" :loading="partialLoading" :disabled="!selection" @click="onPartialRewrite">
              {{ partialLoading ? '重写中…' : '局部重写' }}
            </a-button>
          </div>
          <!-- 局部结果 -->
          <div v-if="partialResult?.regenerated_text" class="result-box">
            <div class="result-meta">
              <span class="wc-info">{{ partialResult.original_length }} 字 → {{ partialResult.regenerated_length }} 字</span>
              <a-button type="primary" size="small" @click="onApplyPartial">替换原文片段</a-button>
            </div>
            <div class="regen-text">{{ partialResult.regenerated_text }}</div>
          </div>
        </a-tab-pane>

        <!-- 重写历史 -->
        <a-tab-pane key="history" tab="重写历史">
          <a-spin :spinning="loadingHistory">
            <div v-if="!history.length" class="empty-hint">暂无重写记录</div>
            <a-list v-else :data-source="history" size="small">
              <template #renderItem="{ item }">
                <a-list-item>
                  <div class="history-item">
                    <div class="history-meta">
                      <a-tag :color="item.is_applied ? 'green' : 'default'">版本 {{ item.version_number }}</a-tag>
                      <span v-if="item.version_note" class="vn">{{ item.version_note }}</span>
                      <span class="wc">{{ item.original_word_count }} → {{ item.regenerated_word_count }} 字</span>
                      <span class="time">{{ item.created_at?.substring(0, 16) }}</span>
                      <div class="history-actions">
                        <a-button size="small" @click="viewHistory(item)">对比</a-button>
                        <a-button size="small" type="primary" :disabled="item.is_applied === 1" @click="applyHistory(item)">
                          {{ item.is_applied === 1 ? '已应用' : '应用' }}
                        </a-button>
                      </div>
                    </div>
                    <div v-if="item.modification_instructions" class="instr">{{ item.modification_instructions.substring(0, 80) }}</div>
                  </div>
                </a-list-item>
              </template>
            </a-list>
          </a-spin>

          <!-- 对比视图 -->
          <a-modal :open="compareOpen" @cancel="historyDetail = null" title="版本对比" width="90%" :footer="null">
            <div v-if="historyDetail" class="diff-meta">
              <span>相似度：{{ (historyDetail.diff_ratio * 100).toFixed(1) }}%</span>
              <span>原文 {{ historyDetail.original_word_count }} 字 | 重写 {{ historyDetail.regenerated_word_count }} 字</span>
            </div>
            <div v-if="historyDetail" class="diff-container" v-html="diffHtml"></div>
          </a-modal>
        </a-tab-pane>
      </a-tabs>
    </a-modal>
  </span>
</template>

<style scoped>
.action-bar { margin-top: 12px; }
.result-box { background: #F8F6F1; border-radius: 8px; padding: 12px; margin-top: 12px; }
.result-meta { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.wc-info { font-size: 13px; color: #595959; }
.regen-text { font-size: 14px; line-height: 1.8; max-height: 200px; overflow-y: auto; white-space: pre-wrap; }
.partial-bar { display: flex; align-items: center; gap: 12px; }
.selection-preview { background: #EAF0F1; border-radius: 6px; padding: 10px; margin-top: 10px; }
.preview-label { font-size: 12px; color: #4D8088; margin-bottom: 4px; font-weight: 600; }
.preview-text { font-size: 13px; color: #595959; line-height: 1.5; }
.empty-hint { text-align: center; color: #8C8C8C; padding: 30px 0; }
.history-item { width: 100%; }
.history-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.vn { font-size: 13px; color: #2B2B2B; font-weight: 500; }
.wc { font-size: 12px; color: #8C8C8C; }
.time { font-size: 11px; color: #B5C7CB; }
.history-actions { margin-left: auto; display: flex; gap: 6px; }
.instr { font-size: 12px; color: #8C8C8C; margin-top: 4px; }
.diff-meta { display: flex; gap: 20px; font-size: 13px; color: #595959; margin-bottom: 12px; padding: 8px 12px; background: #F8F6F1; border-radius: 6px; }
.diff-container { max-height: 60vh; overflow-y: auto; font-family: monospace; font-size: 13px; line-height: 1.6; }
:deep(.diff-same) { color: #595959; }
:deep(.diff-add) { background: #F6FFED; color: #389E0D; }
:deep(.diff-del) { background: #FFF1F0; color: #CF1322; }
</style>
