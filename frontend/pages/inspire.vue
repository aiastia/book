<script setup lang="ts">
// 灵感模式：逐步向导 + 快速模式
import { useProjectApi } from '~/composables/useProjectApi'
import { apiPost } from '~/composables/useApi'
import { useProject } from '~/composables/useProject'
useHead({ title: '灵感模式 — 墨语' })
const api = useProjectApi()
const msg = useMessage()
const { currentProjectId } = useProject()
const { startLegacy } = useBackgroundTasks()

const mode = ref<'step' | 'quick'>('step')
const idea = ref('')
const loading = ref(false)
const examples = ['一个平凡少年偶然获得神秘系统', '重生回高三，这次我要改写命运', '末世降临，主角拥有特殊能力', '穿越成反派，决定洗白', '都市修仙，隐居闹市']

// 逐步模式状态
const step = ref(0) // 0=idea, 1=title, 2=description, 3=theme, 4=genre, 5=done
const stepResults = reactive({
  title: '',
  description: '',
  theme: '',
  genre: [] as string[],
  protagonist_name: '',
})
// 自定义输入框值（每步一个）
const customInput = reactive({ title: '', description: '', theme: '' })
function applyCustomInput() {
  if (step.value === 1 && customInput.title.trim()) stepResults.title = customInput.title.trim()
  else if (step.value === 2 && customInput.description.trim()) stepResults.description = customInput.description.trim()
  else if (step.value === 3 && customInput.theme.trim()) stepResults.theme = customInput.theme.trim()
}
const currentOptions = ref<any[]>([])
const currentPrompt = ref('')

// 快速模式结果
const quickResult = ref<any>(null)

// 类型输入（快速模式可编辑用）
const genreInputVisible = ref(false)
const genreInputValue = ref('')
const genreInputRef = ref<any>(null)
function showGenreInput() {
  genreInputVisible.value = true
  nextTick(() => genreInputRef.value?.focus?.())
}
function addGenre() {
  const val = genreInputValue.value.trim()
  if (val && quickResult.value) {
    if (Array.isArray(quickResult.value.genre)) {
      if (!quickResult.value.genre.includes(val)) quickResult.value.genre.push(val)
    } else {
      quickResult.value.genre = [val]
    }
  }
  genreInputVisible.value = false
  genreInputValue.value = ''
}

// 创建中状态
const creating = ref(false)
const genStep = ref('')  // 自动生成进度

// 兜底：旧的全局灵感
const legacyResult = ref<any>(null)

async function onStepNext() {
  if (!idea.value.trim()) return
  loading.value = true
  try {
    const stepName = ['title', 'description', 'theme', 'genre'][step.value]
    const body: any = { initial_idea: idea.value }
    if (stepResults.title) body.title = stepResults.title
    if (stepResults.description) body.description = stepResults.description
    if (stepResults.theme) body.theme = stepResults.theme

    let res: any
    // 灵感模式不依赖项目上下文，统一用全局接口（避免项目被删后 404）
    res = await api.globalInspirationStep(stepName, body)
    currentOptions.value = res?.options || []
    currentPrompt.value = res?.prompt || ''
    step.value++
  } catch (e: any) {
    msg.error('生成失败：' + formatError(e))
  } finally {
    loading.value = false
  }
}

function selectOption(opt: string) {
  if (step.value === 1) stepResults.title = opt
  else if (step.value === 2) stepResults.description = opt
  else if (step.value === 3) stepResults.theme = opt
}

function toggleGenre(tag: string) {
  const idx = stepResults.genre.indexOf(tag)
  if (idx >= 0) stepResults.genre.splice(idx, 1)
  else stepResults.genre.push(tag)
}

function onStepFinish() {
  step.value = 5
}

async function onQuickComplete() {
  if (!idea.value.trim()) return
  loading.value = true
  quickResult.value = null
  try {
    const body: any = { initial_idea: idea.value }
    if (stepResults.title) body.title = stepResults.title
    if (stepResults.description) body.description = stepResults.description
    let res: any
    res = await api.globalInspirationQuickComplete(body)
    quickResult.value = res
  } catch (e: any) {
    msg.error('快速补全失败：' + formatError(e))
  } finally {
    loading.value = false
  }
}

async function onCreateProject() {
  const data: any = {
    title: stepResults.title || quickResult.value?.title || '',
    genre: stepResults.genre.join('、') || quickResult.value?.genre || '',
    synopsis: stepResults.description || quickResult.value?.description || '',
  }
  // 主角名字暂存，创建时传给角色生成
  if (stepResults.protagonist_name?.trim()) {
    if (import.meta.client) sessionStorage.setItem('moyu_protagonist_name', stepResults.protagonist_name.trim())
  }
  if (!data.title) { msg.warning('缺少书名，无法创建项目'); return }
  creating.value = true
  try {
    const protagonistName = stepResults.protagonist_name?.trim() || ''
    // 1. 创建项目
    genStep.value = '创建项目...'
    const { createProject: selectAndCreate } = useProject()
    const created = await selectAndCreate(data.title, data.genre, data.synopsis)
    const pid = created.id

    // 2. 提交后台初始化任务（世界观+角色+大纲异步生成）
    genStep.value = '提交生成任务...'
    try {
      const task = await apiPost<any>(`/api/projects/${pid}/init-task`,
        { protagonist_name: protagonistName, chapter_count: 3 }, { timeout: 10000 })
      // 使用统一的后台任务管理，确保浮窗立即显示
      startLegacy(task.task_id)
    } catch (e: any) {
      console.warn('后台任务提交失败，将逐个提交异步任务', e)
      // 兜底：逐个提交异步后台任务（不阻塞页面，可安全关闭网页）
      try {
        const t1 = await apiPost<any>(`/api/projects/${pid}/world-core/generate-async`, {}, { timeout: 5000 })
        startLegacy(t1.task_id)
      } catch { /* 忽略 */ }
      try {
        const t2 = await apiPost<any>(`/api/projects/${pid}/characters/batch-generate-async`,
          { count: 5, requirements: protagonistName ? `主角名字：${protagonistName}` : '' }, { timeout: 5000 })
        startLegacy(t2.task_id)
      } catch { /* 忽略 */ }
      try {
        const t3 = await apiPost<any>(`/api/projects/${pid}/outlines/generate-async`,
          { chapter_count: 10 }, { timeout: 5000 })
        startLegacy(t3.task_id)
      } catch { /* 忽略 */ }
    }

    genStep.value = ''
    msg.success('项目已创建！内容正在后台生成，你可以自由浏览')
    resetAll()
    await navigateTo('/dashboard?pid=' + pid)
  } catch (e: any) {
    genStep.value = ''
    msg.error('创建失败：' + formatError(e))
  } finally {
    creating.value = false
  }
}

function resetAll() {
  step.value = 0
  idea.value = ''
  stepResults.title = ''
  stepResults.description = ''
  stepResults.theme = ''
  stepResults.genre = []
  currentOptions.value = []
  quickResult.value = null
  legacyResult.value = null
}

function pickExample(text: string) { idea.value = text }

// 步骤名称映射
const stepLabels: Record<number, string> = { 0: '输入灵感', 1: '选择书名', 2: '选择简介', 3: '选择主题', 4: '选择类型' }
</script>
<template>
  <PageHeader title="灵感模式" />
  <div class="page-content inspire-page">
    <!-- 模式切换 -->
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <p class="tip" style="margin:0;">输入一句话想法，AI 帮你一步步构建完整故事框架</p>
      <div style="display:flex;align-items:center;gap:8px;">
        <span style="font-size:13px;color:#999;">逐步</span>
        <a-switch :checked="mode === 'quick'" @change="(v: boolean) => mode = v ? 'quick' : 'step'" />
        <span style="font-size:13px;color:#999;">快速</span>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="input-box">
      <a-textarea v-model:value="idea" :rows="3" placeholder="如：一个平凡少年偶然获得神秘系统..." :disabled="loading" style="flex:1;" />
      <div style="display:flex;flex-direction:column;gap:8px;">
        <a-button v-if="mode === 'step'" type="primary" :loading="loading" :disabled="!idea.trim() || step >= 1" @click="onStepNext">
          {{ loading ? 'AI 思考中…' : '开始创意' }}
        </a-button>
        <a-button v-else type="primary" :loading="loading" :disabled="!idea.trim()" @click="onQuickComplete">
          {{ loading ? 'AI 补全中…' : '快速补全' }}
        </a-button>
        <a-button v-if="step > 0 || quickResult" @click="resetAll">重新开始</a-button>
      </div>
    </div>
    <div class="examples">
      <span class="examples-label">试试这些：</span>
      <a-checkable-tag v-for="e in examples" :key="e" :checked="idea === e" @change="pickExample(e)">{{ e }}</a-checkable-tag>
    </div>

    <!-- 逐步模式 -->
    <template v-if="mode === 'step'">
      <!-- 步骤进度 -->
      <div v-if="step > 0 && step < 5" class="step-progress">
        <a-steps :current="step - 1" size="small" style="margin-bottom:20px;">
          <a-step title="书名" />
          <a-step title="简介" />
          <a-step title="主题" />
          <a-step title="类型" />
        </a-steps>
      </div>

      <a-skeleton v-if="loading" active :paragraph="{ rows: 6 }" />

      <!-- 步骤选择 -->
      <template v-else-if="step >= 1 && step <= 4">
        <a-card style="margin-bottom:16px;">
          <h3 style="font-size:15px;color:#4D8088;margin-bottom:12px;">{{ stepLabels[step] }}</h3>
          <p v-if="currentPrompt" style="color:#666;font-size:14px;margin-bottom:16px;">{{ currentPrompt }}</p>
          <div class="options-grid">
            <div
              v-for="(opt, idx) in currentOptions"
              :key="idx"
              class="option-card"
              :class="{
                selected: step === 1 ? stepResults.title === opt : step === 2 ? stepResults.description === opt : step === 3 ? stepResults.theme === opt : false,
              }"
              @click="selectOption(opt)"
            >
              <div class="option-label">{{ typeof opt === 'string' ? opt : opt.name || opt.title || JSON.stringify(opt) }}</div>
              <div v-if="typeof opt === 'object' && opt.description" class="option-desc">{{ opt.description }}</div>
            </div>
          </div>
          <!-- 自定义输入：不满意 AI 选项可自己输入 -->
          <div v-if="step <= 3" class="custom-input-box">
            <span class="custom-label">✍️ 不满意？自己输入：</span>
            <a-input
              v-model:value="customInput[(['', 'title', 'description', 'theme'])[step]]"
              :placeholder="step === 1 ? '输入你想要的书名' : step === 2 ? '输入你想要的简介' : '输入你想要的主题'"
              @pressEnter="applyCustomInput"
            />
            <a-button size="small" @click="applyCustomInput">使用</a-button>
          </div>
          <!-- 类型步骤特殊处理：多选标签 -->
          <div v-if="step === 4" class="genre-tags">
            <a-checkable-tag
              v-for="(opt, idx) in currentOptions"
              :key="idx"
              :checked="stepResults.genre.includes(typeof opt === 'string' ? opt : opt.name)"
              @change="toggleGenre(typeof opt === 'string' ? opt : opt.name)"
              style="font-size:14px;padding:4px 12px;"
            >{{ typeof opt === 'string' ? opt : opt.name || JSON.stringify(opt) }}</a-checkable-tag>
          </div>
          <div style="margin-top:16px;display:flex;gap:8px;">
            <a-button @click="step--">上一步</a-button>
            <a-button v-if="step < 4" type="primary" :disabled="step === 1 ? !stepResults.title : step === 2 ? !stepResults.description : step === 3 ? !stepResults.theme : stepResults.genre.length === 0" @click="onStepNext">下一步</a-button>
            <a-button v-else type="primary" @click="onStepFinish">完成</a-button>
          </div>
        </a-card>
      </template>

      <!-- 完成汇总 -->
      <a-card v-else-if="step === 5" hoverable>
        <h3 style="font-size:18px;color:#4D8088;margin-bottom:16px;">故事框架完成！</h3>
        <div class="result-section"><h4>书名</h4><p>{{ stepResults.title }}</p></div>
        <div class="result-section"><h4>简介</h4><p>{{ stepResults.description }}</p></div>
        <div class="result-section"><h4>主题</h4><p>{{ stepResults.theme }}</p></div>
        <div class="result-section"><h4>类型</h4><div><a-tag v-for="g in stepResults.genre" :key="g" style="margin-right:6px;">{{ g }}</a-tag></div></div>
        <div class="result-section"><h4>主角名字（可选）</h4><a-input v-model:value="stepResults.protagonist_name" placeholder="留空则 AI 生成" style="max-width:240px;" /></div>
        <a-alert v-if="creating && genStep" :message="genStep + '...'" type="info" show-icon style="margin-top:16px;" />
        <div style="margin-top:20px;display:flex;gap:8px;">
          <a-button type="primary" :loading="creating" @click="onCreateProject">
            <span v-if="creating && genStep">{{ genStep }}…</span>
            <span v-else-if="creating">创建中…</span>
            <span v-else>✨ 创建项目并自动生成内容</span>
          </a-button>
          <a-button @click="resetAll">重新开始</a-button>
        </div>
      </a-card>
    </template>

    <!-- 快速模式结果（可编辑） -->
    <template v-if="mode === 'quick' && quickResult">
      <a-card hoverable>
        <div style="margin-bottom:16px;">
          <a-tag color="blue" size="small">✨ AI 补全完成，你可以修改以下内容后创建项目</a-tag>
        </div>
        <a-form layout="vertical">
          <a-form-item label="书名"><a-input v-model:value="quickResult.title" placeholder="书名" /></a-form-item>
          <a-form-item label="简介"><a-textarea v-model:value="quickResult.description" :rows="3" placeholder="简介" /></a-form-item>
          <a-form-item label="主题"><a-input v-model:value="quickResult.theme" placeholder="主题" /></a-form-item>
          <a-form-item label="类型">
            <a-input v-if="!Array.isArray(quickResult.genre)" v-model:value="quickResult.genre" placeholder="类型" />
            <div v-else>
              <a-tag v-for="(g, i) in quickResult.genre" :key="i" closable size="small" style="margin-right:6px;" @close="quickResult.genre.splice(i, 1)">{{ g }}</a-tag>
              <a-input v-if="genreInputVisible" ref="genreInputRef" v-model:value="genreInputValue" size="small" style="width:120px;" placeholder="新类型" @press-enter="addGenre" @blur="addGenre" />
              <a-button v-else size="small" type="dashed" @click="showGenreInput">+ 添加类型</a-button>
            </div>
          </a-form-item>
          <a-row :gutter="12">
            <a-col :span="12"><a-form-item label="叙事视角"><a-select v-model:value="quickResult.narrative_pov" style="width:100%"><a-select-option label="第三人称" value="第三人称" /><a-select-option label="第一人称" value="第一人称" /><a-select-option label="全知视角" value="全知视角" /><a-select-option label="第二人称" value="第二人称" /></a-select></a-form-item></a-col>
            <a-col :span="12"><a-form-item label="目标字数"><a-input-number v-model:value="quickResult.target_word_count" :min="10000" :max="5000000" :step="10000" style="width:100%" /></a-form-item></a-col>
          </a-row>
        </a-form>
        <a-alert v-if="creating && genStep" :message="genStep + '...'" type="info" show-icon style="margin-top:16px;" />
        <div style="margin-top:20px;display:flex;gap:8px;">
          <a-button type="primary" :loading="creating" @click="onCreateProject">
            <span v-if="creating && genStep">{{ genStep }}…</span>
            <span v-else-if="creating">创建中…</span>
            <span v-else>✨ 创建项目并自动生成内容</span>
          </a-button>
          <a-button @click="resetAll">重新开始</a-button>
        </div>
      </a-card>
    </template>
  </div>
</template>
<style scoped>
.inspire-page{max-width:760px;margin:0 auto;}
.tip{color:#888;font-size:13px;margin-bottom:16px;}
.input-box{display:flex;gap:12px;margin-bottom:16px;}
.examples{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:24px;}
.examples-label{font-size:13px;color:#999;}
.options-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin-bottom:16px;}
.option-card{border:2px solid #e5e7eb;border-radius:8px;padding:12px 16px;cursor:pointer;transition:all .15s;}
.option-card:hover{border-color:#B8CDD1;background:#F0F5F5;}
.option-card.selected{border-color:#4D8088;background:#EAF0F1;}
.option-label{font-size:14px;font-weight:500;line-height:1.6;}
.option-desc{font-size:12px;color:#888;margin-top:4px;line-height:1.5;}
.genre-tags{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px;}
.result-section{margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid #f0f0f0;}
.result-section:last-child{border-bottom:none;}
.result-section h4{font-size:14px;color:#666;margin-bottom:6px;}
.result-section p{font-size:14px;line-height:1.8;color:#333;}
.step-progress{margin-bottom:8px;}
.custom-input-box{display:flex;align-items:center;gap:8px;margin-top:16px;padding-top:12px;border-top:1px dashed #E8E4DC;}
.custom-label{font-size:13px;color:#8C8C8C;white-space:nowrap;}
</style>
