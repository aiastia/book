<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { API } from '~/composables/api'
import { CheckOutlined } from '@ant-design/icons-vue'
import type { AIModelConfig } from '~/composables/api/types'
useHead({ title: 'AI 设置 — 墨语' })
const msg = useMessage()
const { data: models, refresh: refresh } = await useFetch<AIModelConfig[]>(() => `${useRuntimeConfig().public.apiBase}/api/ai-models`)
const showAdd = ref(false)
const editing = ref<any>(null)
const isClient = ref(false) // SSR hydration 保护：这些 ref 在客户端才初始化
onMounted(() => { isClient.value = true })
const form = reactive({
  id: 0, name: '默认', base_url: '', api_key: '', model: 'gpt-4o',
  temperature: 85, top_p: 90, max_tokens: 8192, is_default: false,
  reasoning_model: false,
  reasoning_effort: 'low',
  thinking_mode: 'auto',
  thinking_params: '',
  frequency_penalty: null as number | null, presence_penalty: null as number | null,
  // 灵感模式独立参数（null=跟随全局/不发送）
  inspiration_temperature: null as number | null,
  inspiration_top_p: null as number | null,
  inspiration_frequency_penalty: null as number | null,
  inspiration_presence_penalty: null as number | null,
  inspiration_custom: false,
  backend_type: 'openai' as string,
  provider: 'openai' as 'openai' | 'anthropic' | 'gemini',
  embedding_model: '' as string,
  // Diff Rewrite 润色 API（独立，可选）
  rewrite_base_url: '' as string,
  rewrite_api_key: '' as string,
  rewrite_model: '' as string,
  // 图像生成 API（独立，可选）
  image_base_url: '' as string,
  image_api_key: '' as string,
  image_model: '' as string,
})
const testing = ref<number | null>(null)
// 模型测试结果持久化到 localStorage，刷新页面也能看到上次的测试状态
const TEST_RESULT_KEY = 'moyu_ai_test_results'
const testResult = ref<Record<number, string>>(
  JSON.parse((typeof localStorage !== 'undefined' && localStorage.getItem(TEST_RESULT_KEY)) || '{}')
)
// 监听变化自动保存
watch(testResult, (v) => {
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(TEST_RESULT_KEY, JSON.stringify(v))
  }
}, { deep: true })
const fetchingModels = ref(false)
const remoteModels = ref<Array<{ id: string; owned_by: string }>>([])
const activeModelId = ref<number | null>(null)
const saving = ref(false)

// 状态统计
const stats = computed(() => {
  const list = models.value || []
  const total = list.length
  const connected = list.filter((_: any) => testResult.value[_.id]?.startsWith('✅')).length
  return { total, connected }
})

// 判断 provider
function getProvider(m: any) {
  const url = (m.base_url || '').toLowerCase()
  if (url.includes('openai')) return { name: 'OpenAI', color: '#10a37f', icon: 'O' }
  if (url.includes('anthropic') || url.includes('claude')) return { name: 'Claude', color: '#d97706', icon: 'C' }
  if (url.includes('gemini') || url.includes('google')) return { name: 'Gemini', color: '#4285f4', icon: 'G' }
  if (url.includes('deepseek')) return { name: 'DeepSeek', color: '#4f46e5', icon: 'D' }
  if (url.includes('moonshot') || url.includes('kimi')) return { name: 'Moonshot', color: '#6366f1', icon: 'M' }
  return { name: '自定义', color: '#6b7280', icon: '?' }
}

function openAdd() {
  editing.value = null
  Object.assign(form, {
    id: 0, name: '默认', base_url: '', api_key: '', model: 'gpt-4o',
    temperature: 85, top_p: 90, max_tokens: 8192, is_default: false,
    reasoning_model: false,
    frequency_penalty: null, presence_penalty: null,
    inspiration_temperature: null, inspiration_top_p: null,
    inspiration_frequency_penalty: null, inspiration_presence_penalty: null,
    inspiration_custom: false,
    backend_type: 'openai', provider: 'openai', embedding_model: '',
    rewrite_base_url: '', rewrite_api_key: '', rewrite_model: '',
    image_base_url: '', image_api_key: '', image_model: '',
  })
  remoteModels.value = []
  modelSearch.value = ''
  showAdd.value = true
}
function openEdit(m: any) {
  editing.value = m
  Object.assign(form, {
    ...m, api_key: '',
    backend_type: m.backend_type || 'openai',
    provider: m.provider || m.backend_type || 'openai',
    embedding_model: m.embedding_model || '',
    reasoning_model: m.reasoning_model ?? false,
    reasoning_effort: m.reasoning_effort || 'low',
    thinking_mode: m.thinking_mode || 'auto',
    thinking_params: m.thinking_params || '',
    inspiration_temperature: m.inspiration_temperature ?? null,
    inspiration_top_p: m.inspiration_top_p ?? null,
    inspiration_frequency_penalty: m.inspiration_frequency_penalty ?? null,
    inspiration_presence_penalty: m.inspiration_presence_penalty ?? null,
    inspiration_custom: m.inspiration_custom ?? false,
  })
  remoteModels.value = []
  modelSearch.value = ''
  showAdd.value = true
}
async function onSave() {
  saving.value = true
  try {
    if (editing.value) {
      await API.ai.updateModel(form.id, { ...form })
    } else {
      const { id } = await API.ai.createModel({ ...form })
      if (form.is_default) await API.ai.updateModel(id, { is_default: true })
    }
    showAdd.value = false
    await refresh()
  } catch (e: any) {
    msg.error('保存失败：' + formatError(e))
  } finally {
    saving.value = false
  }
}
async function onDelete(id: number) {
  if (!await msg.confirm('确认删除此模型配置？')) return
  try { await API.ai.deleteModel(id); delete testResult.value[id]; await refresh() } catch (e: any) { msg.error('删除失败') }
}
async function onTest(id: number) {
  testing.value = id
  testResult.value[id] = '测试中…'
  try {
    const r = await API.ai.testModel(id)
    const parts = [`✅ ${r.reply}`]
    // 双重信号判断推理状态
    if (r.thinking_active) {
      parts.push(`⚠️ 推理仍在运行！`)
      const reasons: string[] = []
      if (r.reasoning_tokens > 0) reasons.push(`reasoning_tokens=${r.reasoning_tokens}`)
      if (r.reasoning_content_len > 0) reasons.push(`思维过程=${r.reasoning_content_len}字`)
      parts.push(`（${reasons.join('，')}）`)
    } else {
      parts.push(`🧢 推理已关闭（reasoning_tokens=0，无思维过程）`)
    }
    parts.push(`mode=${r.thinking_mode || 'auto'}`)
    testResult.value[id] = parts.join(' | ')
  } catch (e: any) {
    testResult.value[id] = `❌ ${formatError(e, '失败')}`
  } finally { testing.value = null }
}
async function onSetDefault(id: number) {
  try { await API.ai.updateModel(id, { is_default: true }); await refresh() } catch (e: any) { msg.error('设置失败') }
}

/** 从远程 API 获取模型列表 */
async function fetchModels() {
  if (!form.base_url) {
    msg.warning('请先填写 Base URL')
    return
  }
  modelSearch.value = ''
  // 编辑模式且未填 Key：用后端已存 Key 拉取（无需重复填写）
  if (editing.value && !form.api_key) {
    fetchingModels.value = true
    remoteModels.value = []
    try {
      const r = await API.ai.fetchModelRemoteModels(form.id)
      remoteModels.value = r.models || []
      if (remoteModels.value.length === 0) msg.warning('未获取到可用模型')
    } catch (e: any) {
      msg.error('获取失败：' + formatError(e))
    } finally {
      fetchingModels.value = false
    }
    return
  }
  if (!form.api_key) {
    msg.warning('请先填写 API Key')
    return
  }
  fetchingModels.value = true
  remoteModels.value = []
  try {
    const r = await API.ai.fetchRemoteModels(form.base_url, form.api_key, form.provider)
    remoteModels.value = r.models || []
    if (remoteModels.value.length === 0) {
      msg.warning('未获取到可用模型')
    }
  } catch (e: any) {
    msg.error('获取失败：' + formatError(e))
  } finally {
    fetchingModels.value = false
  }
}

function selectRemoteModel(id: string) {
  form.model = id
}

// 远程模型搜索过滤
const modelSearch = ref('')
const filteredRemoteModels = computed(() => {
  if (!modelSearch.value) return remoteModels.value
  const q = modelSearch.value.toLowerCase()
  return remoteModels.value.filter((rm: any) => rm.id.toLowerCase().includes(q))
})

// Provider 元信息
const providerMeta: Record<string, { label: string; icon: string; defaultUrl: string; defaultModel: string }> = {
  openai: { label: 'OpenAI 兼容', icon: '🤖', defaultUrl: 'https://api.openai.com/v1', defaultModel: 'gpt-4o' },
  anthropic: { label: 'Anthropic Claude', icon: '🧠', defaultUrl: 'https://api.anthropic.com/v1', defaultModel: 'claude-sonnet-4-5' },
  gemini: { label: 'Google Gemini', icon: '✨', defaultUrl: 'https://generativelanguage.googleapis.com/v1beta', defaultModel: 'gemini-2.0-flash' },
}
function onProviderChange(p: string) {
  form.provider = p as any
  form.backend_type = p === 'openai' ? 'openai' : p
  // 自动填充默认 URL 和模型（仅新增时）
  if (!editing.value) {
    const meta = providerMeta[p]
    if (meta) {
      form.base_url = meta.defaultUrl
      form.model = meta.defaultModel
    }
  }
  remoteModels.value = []
}

// Embedding 测试
const testingEmbed = ref(false)
const embedResult = ref('')
async function onTestEmbedding() {
  if (!form.base_url) {
    msg.warning('请先填写 Base URL')
    return
  }
  if (!form.api_key) {
    msg.warning('请填写 API Key 后再测试')
    return
  }
  testingEmbed.value = true
  embedResult.value = '测试中…'
  try {
    const r = await API.ai.testEmbedding(form.base_url, form.api_key, form.embedding_model || 'text-embedding-3-small')
    embedResult.value = `✅ 向量维度 ${r.dim}，模型 ${r.model}`
    msg.success('Embedding 接口可用')
  } catch (e: any) {
    embedResult.value = `❌ ${formatError(e)}`
  } finally {
    testingEmbed.value = false
  }
}

// 温度/TopP 转换 (存储0-100整数, 显示0-1浮点)
const tempDisplay = computed({
  get: () => (form.temperature / 100).toFixed(2),
  set: (v: string) => { form.temperature = Math.round(parseFloat(v) * 100) }
})
const topPDisplay = computed({
  get: () => (form.top_p / 100).toFixed(2),
  set: (v: string) => { form.top_p = Math.round(parseFloat(v) * 100) }
})

// 自定义参数预设：当文本框内容匹配某个预设时，下拉框显示对应项
const thinkingParamsPreset = computed(() => {
  const known = [
    '', '{"thinking":{"type":"disabled"}}', '{"thinking":{"type":"enabled"}}',
    '{"enable_thinking":false}', '{"enable_thinking":true}',
    '{"reasoning_effort":"low"}', '{"reasoning_effort":"medium"}',
    '{"reasoning_effort":"high"}', '{"reasoning_effort":"off"}',
    '{"thinking":{"type":"enabled","budget_tokens":8000}}',
  ]
  return known.includes(form.thinking_params) ? form.thinking_params : undefined
})
function onSelectPreset(val: any) {
  form.thinking_params = val || ''
}

// 频率/存在惩罚显示转换（null=不发送，-200~200 映射到 -2.00~2.00）
function penaltyDisplay(val: number | null): string {
  if (val == null) return '不发送'
  return (val / 100).toFixed(2)
}
function penaltySliderVal(val: number | null): number {
  return val ?? 0
}

// 灵感模式温度递减表常量
const INSP_BASE = { title: 0.8, description: 0.65, theme: 0.55, genre: 0.45 }
// 根据滑块值计算各阶段实际温度
const inspirationStageTemps = computed(() => {
  const ref = form.inspiration_temperature
  if (ref == null) return INSP_BASE  // 留空 → 显示默认表
  const ratio = (ref / 100) / INSP_BASE.title
  const r: Record<string, number> = {}
  for (const [k, v] of Object.entries(INSP_BASE)) {
    r[k] = parseFloat((v * ratio).toFixed(2))
  }
  return r
})

// 默认模型的参数
const defaultModel = computed(() => (models.value || []).find((m: any) => m.is_default))

// ===== 润色用 API =====
const rewriteForm = reactive({ base_url: '', api_key: '', model: '' })
const rewriteEnabled = ref(false)
const rewriteOk = ref(false)
const savingRewrite = ref(false)
const testingRewrite = ref(false)
const rewriteResult = ref('')
const rewriteLoaded = ref(false)

// ===== 图像生成 API =====
const imageForm = reactive({ base_url: '', api_key: '', model: '' })
const savingImage = ref(false)
const imageLoaded = ref(false)

function loadRewriteConfig() {
  if (rewriteLoaded.value || !models.value?.length) return
  const def = defaultModel.value || models.value[0]
  if (!def) return
  rewriteForm.base_url = def.rewrite_base_url || ''
  rewriteForm.api_key = def.rewrite_api_key || ''
  rewriteForm.model = def.rewrite_model || ''
  rewriteEnabled.value = !!(def.rewrite_base_url || def.rewrite_api_key || def.rewrite_model)
  rewriteLoaded.value = true
}

function loadImageConfig() {
  if (imageLoaded.value || !models.value?.length) return
  const def = defaultModel.value || models.value[0]
  if (!def) return
  imageForm.base_url = def.image_base_url || ''
  imageForm.api_key = def.image_api_key || ''
  imageForm.model = def.image_model || ''
  imageLoaded.value = true
}
watch(models, () => { loadRewriteConfig(); loadImageConfig() }, { immediate: true })

async function onSaveRewrite() {
  const def = defaultModel.value || models.value?.[0]
  if (!def) { msg.warning('请先添加一个 AI 模型'); return }
  savingRewrite.value = true
  try {
    await API.ai.updateModel(def.id, {
      rewrite_base_url: rewriteForm.base_url || '',
      rewrite_api_key: rewriteForm.api_key || '',
      rewrite_model: rewriteForm.model || '',
    })
    rewriteOk.value = false
    msg.success('润色 API 已保存')
  } catch (e: any) { msg.error('保存失败') }
  finally { savingRewrite.value = false }
}

async function onSaveImage() {
  const def = defaultModel.value || models.value?.[0]
  if (!def) { msg.warning('请先添加一个 AI 模型'); return }
  savingImage.value = true
  try {
    await API.ai.updateModel(def.id, {
      image_base_url: imageForm.base_url || '',
      image_api_key: imageForm.api_key || '',
      image_model: imageForm.model || '',
    })
    msg.success('图像 API 已保存')
  } catch (e: any) { msg.error('保存失败') }
  finally { savingImage.value = false }
}

async function onTestRewrite() {
  if (!rewriteForm.base_url) { msg.warning('请先填写 Base URL'); return }
  if (!rewriteForm.api_key) { msg.warning('请填写 API Key 后再测试'); return }
  testingRewrite.value = true
  rewriteResult.value = '测试中…'
  try {
    const r = await API.ai.testRewrite(rewriteForm.base_url, rewriteForm.api_key, rewriteForm.model || 'gpt-4o-mini')
    rewriteOk.value = !!(r as any)?.ok
    rewriteResult.value = (r as any)?.ok ? `✅ ${(r as any).msg}` : `❌ ${(r as any).msg}`
  } catch (e: any) {
    rewriteOk.value = false
    rewriteResult.value = '❌ ' + formatError(e)
  } finally { testingRewrite.value = false }
}

const fetchingRewriteModels = ref(false)
const rewriteRemoteModels = ref<Array<{ id: string }>>([])

async function fetchRewriteModels() {
  if (!rewriteForm.base_url) { msg.warning('请先填写 Base URL'); return }
  fetchingRewriteModels.value = true
  try {
    const r = await API.ai.fetchRewriteRemoteModels(rewriteForm.base_url, rewriteForm.api_key)
    rewriteRemoteModels.value = (r as any).models || []
    if (!rewriteRemoteModels.value.length) msg.warning('未获取到可用模型')
  } catch (e: any) { msg.error('获取失败：' + formatError(e)) }
  finally { fetchingRewriteModels.value = false }
}
function selectRewriteModel(id: string) {
  rewriteForm.model = id
  rewriteRemoteModels.value = []
  fetchingRewriteModels.value = false
}
</script>

<template>
  <PageHeader title="AI 模型设置" back="/books" />
  <div class="page-content">
    <!-- 顶部状态卡片（依赖 localStorage 测试结果，仅客户端渲染以避免 SSR hydration  mismatch） -->
    <div v-if="isClient" class="stats-bar">
      <a-card hoverable class="stat-card-el">
        <a-statistic title="已配置模型" :value="stats.total" />
      </a-card>
      <a-card hoverable class="stat-card-el">
        <a-statistic title="连接正常" :value="stats.connected">
          <template #suffix>
            <span style="font-size:12px;color:#4D8088;"></span>
          </template>
        </a-statistic>
      </a-card>
    </div>

    <!-- API 密钥管理 -->
    <a-card class="section-card">
      <template #title>
        <div class="section-header">
          <h2>API 密钥管理</h2>
          <a-button type="primary" @click="openAdd">+ 添加模型</a-button>
        </div>
      </template>
      <p class="section-desc">配置各 AI 模型对应的 API 密钥。点击卡片可切换默认模型。</p>

      <div v-if="isClient && models && models.length" class="model-cards">
        <a-card
          v-for="m in models" :key="m.id"
          hoverable
          class="provider-card"
          :class="{ active: m.is_default }"
          @click="activeModelId = activeModelId === m.id ? null : m.id"
        >
          <div class="provider-left">
            <div class="provider-icon" :style="{ background: getProvider(m).color }">
              {{ getProvider(m).icon }}
            </div>
            <a-tag
              :color="testResult[m.id]?.startsWith('✅') ? 'success' : (testResult[m.id]?.startsWith('❌') ? 'error' : 'default')"
            >
              {{ testResult[m.id]?.startsWith('✅') ? '已连接' : (testResult[m.id]?.startsWith('❌') ? '异常' : '待测试') }}
            </a-tag>
          </div>
          <div class="provider-info">
            <div class="provider-name">
              {{ m.name }}
              <a-tag v-if="m.is_default" color="success">默认</a-tag>
            </div>
            <div class="provider-model">{{ m.model }}</div>
            <div class="provider-url">{{ m.base_url }}</div>
          </div>
          <div class="provider-check" v-if="m.is_default">✓</div>
          <!-- 操作按钮 -->
          <div class="provider-actions" v-if="activeModelId === m.id" @click.stop>
            <a-button v-if="!m.is_default" type="primary" size="small" @click="onSetDefault(m.id)">设为默认</a-button>
            <a-button size="small" :loading="testing===m.id" @click="onTest(m.id)">
              {{ testing === m.id ? '测试中...' : '⚡ 测试连接' }}
            </a-button>
            <a-button size="small" @click="openEdit(m)">编辑</a-button>
            <a-button size="small" danger @click="onDelete(m.id)">删除</a-button>
          </div>
          <div v-if="testResult[m.id]" class="test-result" :class="{ ok: testResult[m.id].startsWith('✅'), err: testResult[m.id].startsWith('❌') }">
            {{ testResult[m.id] }}
          </div>
        </a-card>
      </div>
      <a-empty v-else-if="isClient" description="暂无模型配置，点击「添加模型」开始" />
    </a-card>

    <!-- 默认模型与参数（依赖客户端状态，避免 SSR hydration mismatch） -->
    <a-card v-if="isClient && models && models.length" class="section-card">
      <template #title>
        <h2>默认模型与参数</h2>
      </template>
      <p class="section-desc">选择各模型的默认参数，请谨慎设置参数。</p>

      <div class="params-grid">
        <div class="param-card">
          <label>默认模型</label>
          <a-select
            :value="defaultModel?.id"
            @change="onSetDefault"
            style="width:100%;"
          >
            <a-select-option v-for="m in models" :key="m.id" :value="m.id">{{ m.model }}{{ m.is_default ? ' (默认)' : '' }}</a-select-option>
          </a-select>
        </div>
      </div>

      <!-- 全局参数滑块 -->
      <div class="global-params">
        <h3>全局模型参数</h3>
        <div class="slider-group">
          <div class="slider-header">
            <label>Temperature（随机性）</label>
            <span class="slider-value">{{ (defaultModel?.temperature ?? 70) / 100 }}</span>
          </div>
          <a-slider :value="(defaultModel?.temperature ?? 70) / 100" :min="0" :max="2" :step="0.01" disabled />
          <div class="slider-range"><span>0 (精确)</span><span>2 (创造)</span></div>
        </div>
        <div class="slider-group">
          <div class="slider-header">
            <label>Top P（核采样）</label>
            <span class="slider-value">{{ (defaultModel?.top_p ?? 90) / 100 }}</span>
          </div>
          <a-slider :value="(defaultModel?.top_p ?? 90) / 100" :min="0" :max="1" :step="0.01" disabled />
          <div class="slider-range"><span>0</span><span>1</span></div>
        </div>
        <div class="slider-group">
          <div class="slider-header">
            <label>Max Tokens（最大长度）</label>
            <span class="slider-value">{{ defaultModel?.max_tokens ?? 4096 }}</span>
          </div>
          <a-slider :value="defaultModel?.max_tokens ?? 4096" :min="2000" :max="200000" :step="1000" disabled />
          <div class="slider-range"><span>2000</span><span>200000</span></div>
        </div>
        <div class="slider-group">
          <div class="slider-header">
            <label>频率惩罚（减少重复用词）</label>
            <span class="slider-value">{{ penaltyDisplay(defaultModel?.frequency_penalty ?? null) }}</span>
          </div>
          <a-slider :value="penaltySliderVal(defaultModel?.frequency_penalty ?? null)" :min="-200" :max="200" :step="1" disabled />
          <div class="slider-range"><span>-2.0</span><span>0</span><span>2.0</span></div>
        </div>
        <div class="slider-group">
          <div class="slider-header">
            <label>存在惩罚（引入新话题）</label>
            <span class="slider-value">{{ penaltyDisplay(defaultModel?.presence_penalty ?? null) }}</span>
          </div>
          <a-slider :value="penaltySliderVal(defaultModel?.presence_penalty ?? null)" :min="-200" :max="200" :step="1" disabled />
          <div class="slider-range"><span>-2.0</span><span>0</span><span>2.0</span></div>
        </div>
      </div>
    </a-card>
  </div>

  <!-- 添加/编辑模型弹窗 -->
  <a-modal
    v-model:open="showAdd"
    :title="editing ? '编辑模型' : '添加模型'"
    width="640px"
    :maskClosable="false"
  >
    <!-- 后端类型选择 -->
    <a-form layout="vertical">
      <a-form-item label="AI 厂商（Provider）">
        <a-radio-group v-model:value="form.provider" button-style="solid" @change="(e:any) => onProviderChange(e.target.value)">
          <a-radio-button v-for="(meta, key) in providerMeta" :key="key" :value="key">
            {{ meta.icon }} {{ meta.label }}
          </a-radio-button>
        </a-radio-group>
        <div class="field-hint">
          <span v-if="form.provider === 'openai'">兼容所有 OpenAI 格式接口（DeepSeek / Moonshot / 智谱 / 自建中转等）。<b>推荐</b></span>
          <span v-else-if="form.provider === 'anthropic'">Claude 系列（需通过 OpenAI 兼容代理或原生 SDK）。</span>
          <span v-else-if="form.provider === 'gemini'">Google Gemini 系列。</span>
        </div>
      </a-form-item>

      <div class="form-row-2">
        <a-form-item label="名称 *">
          <a-input v-model:value="form.name" placeholder="例如：OpenAI / Claude / DeepSeek" />
        </a-form-item>
        <a-form-item label="组织 ID">
          <a-input placeholder="可选" disabled />
        </a-form-item>
      </div>

        <div class="form-row-2">
          <a-form-item label="Base URL *">
            <a-input v-model:value="form.base_url" :placeholder="providerMeta[form.provider]?.defaultUrl || 'https://api.openai.com/v1'" />
          </a-form-item>
          <a-form-item label="API Key">
            <a-input-password v-model:value="form.api_key" autocomplete="off" :placeholder="editing ? '留空不修改（获取模型时使用已存 Key）' : 'sk-...'" />
            <div class="field-hint">{{ editing ? '留空保留原密钥，获取模型时自动使用已存 Key' : '在对应平台获取的 API Key' }}</div>
          </a-form-item>
        </div>

        <!-- 获取模型按钮 -->
        <div class="fetch-models-bar">
          <a-button :loading="fetchingModels" @click="fetchModels">
            {{ fetchingModels ? '获取中...' : '🔍 获取可用模型' }}
          </a-button>
          <a-tag v-if="remoteModels.length" color="success">找到 {{ remoteModels.length }} 个模型</a-tag>
        </div>

        <!-- 远程模型搜索 -->
        <a-input
          v-if="remoteModels.length"
          v-model:value="modelSearch"
          placeholder="搜索模型…"
          allow-clear
          size="small"
          style="margin-bottom: 8px;"
        />

        <!-- 远程模型列表 -->
        <div v-if="remoteModels.length" class="remote-models">
          <div
            v-for="rm in filteredRemoteModels" :key="rm.id"
            class="remote-model-item"
            :class="{ selected: form.model === rm.id }"
            @click="selectRemoteModel(rm.id)"
          >
            <span class="rm-id">{{ rm.id }}</span>
            <CheckOutlined v-if="form.model === rm.id" :style="{ color: '#4D8088' }" />
          </div>
        </div>

        <a-form-item label="模型 ID *">
          <a-input v-model:value="form.model" placeholder="gpt-4o 或从上方列表选择" />
        </a-form-item>

      <!-- Embedding 模型配置（用于记忆向量检索） -->
      <a-divider orientation="left">向量检索配置（可选）</a-divider>
      <a-alert
        message="用于故事记忆的语义检索。填写后，章节分析提取的记忆将自动向量化，生成新章节时召回相关前情。"
        type="info" show-icon :closable="false" style="margin-bottom:12px;"
      />
      <div class="form-row-2">
        <a-form-item label="Embedding 模型">
          <a-input v-model:value="form.embedding_model" placeholder="text-embedding-3-small（留空则不启用向量检索）" />
        </a-form-item>
        <a-form-item label=" ">
          <a-button :loading="testingEmbed" :disabled="!form.base_url" @click="onTestEmbedding">
            {{ testingEmbed ? '测试中...' : '🧪 测试 Embedding' }}
          </a-button>
        </a-form-item>
      </div>
      <div v-if="embedResult" class="test-result" :class="{ ok: embedResult.startsWith('✅'), err: embedResult.startsWith('❌') }">
        {{ embedResult }}
      </div>

      <!-- 参数设置 -->
      <a-divider orientation="left">模型参数</a-divider>

      <div class="slider-group">
        <div class="slider-header">
          <label>Temperature（随机性）</label>
          <a-tag color="default">{{ tempDisplay }}</a-tag>
        </div>
        <a-slider v-model:value="form.temperature" :min="0" :max="200" :step="1" :disabled="form.reasoning_model" />
        <div class="slider-range"><span>0 (精确)</span><span>2 (创造)</span></div>
      </div>
      <div class="slider-group">
        <div class="slider-header">
          <label>Top P（核采样）</label>
          <a-tag color="default">{{ topPDisplay }}</a-tag>
        </div>
        <a-slider v-model:value="form.top_p" :min="0" :max="100" :step="1" :disabled="form.reasoning_model" />
        <div class="slider-range"><span>0</span><span>1</span></div>
      </div>
      <div class="slider-group">
        <div class="slider-header">
          <label>Max Tokens（最大长度）</label>
          <a-tag color="default">{{ form.max_tokens }}</a-tag>
        </div>
          <a-slider v-model:value="form.max_tokens" :min="2000" :max="200000" :step="1000" />
        <div class="slider-range"><span>512</span><span>128000</span></div>
      </div>

      <a-divider orientation="left">高级参数</a-divider>
      <p style="font-size:12px;color:#999;margin-bottom:12px;">以下参数若为"不发送"，则 API 调用时不携带该字段（兼容不支持的模型）</p>

      <div class="slider-group">
        <div class="slider-header">
          <label>频率惩罚（减少重复用词）</label>
          <a-tag :color="form.frequency_penalty == null ? 'default' : 'blue'">{{ penaltyDisplay(form.frequency_penalty) }}</a-tag>
        </div>
        <a-slider :value="penaltySliderVal(form.frequency_penalty)" :min="-200" :max="200" :step="1" :disabled="form.reasoning_model"
          @change="(v: number) => form.frequency_penalty = v" />
        <div class="slider-range"><span>-2.0 (鼓励重复)</span><span>0</span><span>2.0 (禁止重复)</span></div>
        <a-button size="small" type="link" @click="form.frequency_penalty = null" style="padding:0;margin-top:4px;">重置为不发送</a-button>
      </div>
      <div class="slider-group">
        <div class="slider-header">
          <label>存在惩罚（鼓励新话题）</label>
          <a-tag :color="form.presence_penalty == null ? 'default' : 'blue'">{{ penaltyDisplay(form.presence_penalty) }}</a-tag>
        </div>
        <a-slider :value="penaltySliderVal(form.presence_penalty)" :min="-200" :max="200" :step="1" :disabled="form.reasoning_model"
          @change="(v: number) => form.presence_penalty = v" />
        <div class="slider-range"><span>-2.0 (聚焦主题)</span><span>0</span><span>2.0 (鼓励发散)</span></div>
        <a-button size="small" type="link" @click="form.presence_penalty = null" style="padding:0;margin-top:4px;">重置为不发送</a-button>
      </div>

      <a-form-item>
        <a-switch v-model:checked="form.inspiration_custom" />
        <span style="margin-left: 8px;">自定义灵感参数</span>
        <div style="font-size:12px;color:#999;margin-top:4px;">
          开启后灵感模式使用递减温度表（标题 0.8 → 题材 0.45），下方滑块可覆盖默认值。关闭则跟随全局参数。
        </div>
      </a-form-item>

      <template v-if="form.inspiration_custom">
        <a-divider orientation="left">灵感模式参数</a-divider>

        <div class="slider-group">
          <div class="slider-header">
            <label>Temperature（以标题为基准）</label>
            <a-tag :color="form.inspiration_temperature == null ? 'default' : 'blue'">{{ form.inspiration_temperature == null ? '递减温度表' : (form.inspiration_temperature / 100).toFixed(2) + '（基准）' }}</a-tag>
          </div>
          <a-slider :value="form.inspiration_temperature ?? 70" :min="0" :max="200" :step="1"
            @change="(v: number) => form.inspiration_temperature = v" />
          <div class="slider-range"><span>0</span><span>1</span><span>2</span></div>
          <a-button size="small" type="link" @click="form.inspiration_temperature = null" style="padding:0;margin-top:4px;">使用递减温度表</a-button>
          <div style="display:flex;gap:16px;font-size:12px;color:#888;margin-top:6px;">
            <span v-for="(val, label) in inspirationStageTemps" :key="label" :title="label">
              {{ label }} <b style="color:#4D8088;">{{ val }}</b>
            </span>
          </div>
        </div>

        <div class="slider-group">
          <div class="slider-header">
            <label>Top P（核采样）</label>
            <a-tag :color="form.inspiration_top_p == null ? 'default' : 'blue'">{{ penaltyDisplay(form.inspiration_top_p) }}</a-tag>
          </div>
          <a-slider :value="penaltySliderVal(form.inspiration_top_p)" :min="0" :max="100" :step="1"
            @change="(v: number) => form.inspiration_top_p = v" />
          <div class="slider-range"><span>0</span><span>0.5</span><span>1</span></div>
          <a-button size="small" type="link" @click="form.inspiration_top_p = null" style="padding:0;margin-top:4px;">不发送</a-button>
        </div>

        <div class="slider-group">
          <div class="slider-header">
            <label>频率惩罚（减少重复用词）</label>
            <a-tag :color="form.inspiration_frequency_penalty == null ? 'default' : 'blue'">{{ penaltyDisplay(form.inspiration_frequency_penalty) }}</a-tag>
          </div>
          <a-slider :value="penaltySliderVal(form.inspiration_frequency_penalty)" :min="-200" :max="200" :step="1"
            @change="(v: number) => form.inspiration_frequency_penalty = v" />
          <div class="slider-range"><span>-2.0</span><span>0</span><span>2.0</span></div>
          <a-button size="small" type="link" @click="form.inspiration_frequency_penalty = null" style="padding:0;margin-top:4px;">不发送</a-button>
        </div>

        <div class="slider-group">
          <div class="slider-header">
            <label>存在惩罚（鼓励新话题）</label>
            <a-tag :color="form.inspiration_presence_penalty == null ? 'default' : 'blue'">{{ penaltyDisplay(form.inspiration_presence_penalty) }}</a-tag>
          </div>
          <a-slider :value="penaltySliderVal(form.inspiration_presence_penalty)" :min="-200" :max="200" :step="1"
            @change="(v: number) => form.inspiration_presence_penalty = v" />
          <div class="slider-range"><span>-2.0</span><span>0</span><span>2.0</span></div>
          <a-button size="small" type="link" @click="form.inspiration_presence_penalty = null" style="padding:0;margin-top:4px;">不发送</a-button>
        </div>
      </template>

      <a-form-item>
        <a-switch v-model:checked="form.reasoning_model" />
        <span style="margin-left: 8px;">推理模型</span>
        <div style="font-size:12px;color:#999;margin-top:4px;">
          勾选后：温度强制为 1，不发送 Top P / 惩罚参数。适用于 Kimi K2、DeepSeek-R1、o1/o3 等推理模型
        </div>
        <div v-if="form.reasoning_model" style="margin-top:8px;">
          <span style="font-size:12px;color:#595959;">推理深度：</span>
          <a-select v-model:value="form.reasoning_effort" size="small" style="width:120px;margin-left:8px">
            <a-select-option value="low">低（快，正文优先）</a-select-option>
            <a-select-option value="medium">中（平衡）</a-select-option>
            <a-select-option value="high">高（深度思考）</a-select-option>
          </a-select>
        </div>
      </a-form-item>

      <a-form-item>
        <span style="font-size:14px;color:#333;">Thinking 模式</span>
        <div style="font-size:12px;color:#999;margin-top:4px;">
          控制模型是否进行深度思考。GLM-5 系列默认开启，不关闭会消耗全部 token 导致无输出。
        </div>
        <a-select v-model:value="form.thinking_mode" size="small" style="width:200px;margin-top:8px">
          <a-select-option value="auto">自动（GLM-5 自动关闭，其他不变）</a-select-option>
          <a-select-option value="enabled">开启（强制启用 thinking）</a-select-option>
          <a-select-option value="disabled">关闭（强制关闭 thinking）</a-select-option>
        </a-select>
        <div v-if="form.thinking_mode === 'disabled'" style="font-size:11px;color:#ff4d4f;margin-top:4px;">
          关闭 thinking 后模型响应更快、token 消耗更低。不同厂商参数不同，建议点击「测试连接」验证。
        </div>
        <div v-if="form.thinking_mode !== 'auto'" style="margin-top:8px;">
          <span style="font-size:12px;color:#595959;">自定义参数（JSON）：</span>
          <a-select
            size="small"
            style="width:100%;margin-top:4px;"
            placeholder="选择预设模板或手动编辑下方文本框"
            allow-clear
            :value="thinkingParamsPreset"
            @change="onSelectPreset"
          >
            <a-select-opt-group label="留空（推荐）">
              <a-select-option value="">
                自动映射 — 按模型/厂商自动选择参数（留空即可）
              </a-select-option>
            </a-select-opt-group>
            <a-select-opt-group label="GLM-5 / 智谱">
              <a-select-option value='{"thinking":{"type":"disabled"}}'>关闭思考：thinking disabled</a-select-option>
              <a-select-option value='{"thinking":{"type":"enabled"}}'>开启思考：thinking enabled</a-select-option>
            </a-select-opt-group>
            <a-select-opt-group label="Step / 通义千问 / Kimi / Moonshot">
              <a-select-option value='{"enable_thinking":false}'>关闭思考：enable_thinking false</a-select-option>
              <a-select-option value='{"enable_thinking":true}'>开启思考：enable_thinking true</a-select-option>
            </a-select-opt-group>
            <a-select-opt-group label="OpenAI o1/o3 / DeepSeek-R1">
              <a-select-option value='{"reasoning_effort":"low"}'>低强度：reasoning_effort low</a-select-option>
              <a-select-option value='{"reasoning_effort":"medium"}'>中强度：reasoning_effort medium</a-select-option>
              <a-select-option value='{"reasoning_effort":"high"}'>高强度：reasoning_effort high</a-select-option>
              <a-select-option value='{"reasoning_effort":"off"}'>关闭：reasoning_effort off</a-select-option>
            </a-select-opt-group>
            <a-select-opt-group label="Anthropic / Claude">
              <a-select-option value='{"thinking":{"type":"disabled"}}'>关闭思考</a-select-option>
              <a-select-option value='{"thinking":{"type":"enabled","budget_tokens":8000}}'>开启思考（budget 8000）</a-select-option>
            </a-select-opt-group>
          </a-select>
          <a-textarea v-model:value="form.thinking_params" :rows="3" size="small"
            placeholder='留空 = 自动映射（推荐）&#10;或手动填写 JSON，如 {"enable_thinking": false}'
            style="font-family:monospace;font-size:12px;margin-top:6px;width:100%;" />
          <div style="font-size:11px;color:#999;margin-top:2px;">
            留空 = 按模型/厂商自动映射。选择上方预设或手动编辑 JSON，填入后优先使用。
          </div>
        </div>
      </a-form-item>

      <a-form-item>
        <a-switch v-model:checked="form.is_default" />
        <span style="margin-left: 8px;">设为默认模型</span>
      </a-form-item>
    </a-form>

    <template #footer>
      <a-button @click="showAdd = false">取消</a-button>
      <a-button type="primary" :loading="saving" @click="onSave">保存</a-button>
    </template>
  </a-modal>

  <!-- 润色用 API 配置（独立于章节生成） -->
  <a-card class="section-card" size="small" style="margin-top:16px">
    <template #title>
      <span>🖊️ 润色用 API（去 AI 指纹）</span>
      <a-tag v-if="rewriteEnabled && rewriteOk" color="success" style="margin-left:12px">已连接</a-tag>
      <a-tag v-else-if="rewriteEnabled && !rewriteOk" color="warning" style="margin-left:12px">待测试</a-tag>
      <a-tag v-else color="default" style="margin-left:12px">未启用</a-tag>
    </template>
    <template #extra>
      <a-switch v-model:checked="rewriteEnabled" size="small" style="margin-right:8px" />
      <a-button size="small" :loading="testingRewrite" @click="onTestRewrite">🧪 测试</a-button>
    </template>
    <a-alert
      message="独立于章节生成 API。留空则降级使用默认模型。建议用便宜小模型（如 gpt-4o-mini），一次请求不到一分钱。"
      type="info" show-icon :closable="false" style="margin-bottom:12px;"
    />
    <div class="form-row-2">
      <div>
        <label style="font-size:12px;color:#666">Base URL</label>
        <a-input v-model:value="rewriteForm.base_url" placeholder="https://api.openai.com/v1" size="small" style="margin-top:4px" />
      </div>
      <form @submit.prevent>
        <label style="font-size:12px;color:#666">API Key</label>
        <a-input-password v-model:value="rewriteForm.api_key" autocomplete="off" placeholder="sk-..." size="small" style="margin-top:4px" />
      </form>
    </div>
    <div style="margin-top:12px;display:flex;gap:12px;align-items:flex-end">
      <div>
        <label style="font-size:12px;color:#666">模型</label>
        <a-input v-model:value="rewriteForm.model" placeholder="gpt-4o-mini" size="small" style="margin-top:4px;width:240px" />
      </div>
      <a-button size="small" :loading="fetchingRewriteModels" @click="fetchRewriteModels">获取模型</a-button>
      <a-button type="primary" size="small" :loading="savingRewrite" @click="onSaveRewrite">保存</a-button>
    </div>
    <div v-if="rewriteRemoteModels.length" class="remote-models" style="margin-top:8px">
      <div
        v-for="rm in rewriteRemoteModels" :key="rm.id"
        class="remote-model-item"
        :class="{ selected: rewriteForm.model === rm.id }"
        @click="selectRewriteModel(rm.id)"
      >{{ rm.id }}</div>
    </div>
    <div v-if="rewriteResult" class="test-result" :class="{ ok: rewriteResult.startsWith('✅'), err: rewriteResult.startsWith('❌') }" style="margin-top:8px">
      {{ rewriteResult }}
    </div>
  </a-card>

  <!-- 图像生成 API 配置（用于封面生成） -->
  <a-card class="section-card" size="small" style="margin-top:16px">
    <template #title>
      <span>🖼️ 图像生成 API（封面生成）</span>
    </template>
    <template #extra>
      <a-tag v-if="imageForm.base_url && imageForm.api_key && imageForm.model" color="success" style="margin-left:12px">已配置</a-tag>
      <a-tag v-else color="default" style="margin-left:12px">未配置</a-tag>
    </template>
    <a-alert
      message="独立配置图像生成 API，用于小说封面生成。不填则封面功能只提供提示词，用户可复制到 Midjourney/DALL-E 手动出图。"
      type="info" show-icon :closable="false" style="margin-bottom:12px;"
    />
    <div class="form-row-2">
      <div>
        <label style="font-size:12px;color:#666">Base URL</label>
        <a-input v-model:value="imageForm.base_url" placeholder="https://api.openai.com/v1" size="small" style="margin-top:4px" />
      </div>
      <form @submit.prevent>
        <label style="font-size:12px;color:#666">API Key</label>
        <a-input-password v-model:value="imageForm.api_key" autocomplete="off" placeholder="sk-..." size="small" style="margin-top:4px" />
      </form>
    </div>
    <div style="margin-top:12px;display:flex;gap:12px;align-items:flex-end">
      <div>
        <label style="font-size:12px;color:#666">模型</label>
        <a-input v-model:value="imageForm.model" placeholder="dall-e-3 / flux-1-schnell / sd3" size="small" style="margin-top:4px;width:240px" />
      </div>
      <a-button type="primary" size="small" :loading="savingImage" @click="onSaveImage">保存</a-button>
    </div>
  </a-card>

  <ThinkingModesCard v-if="isClient" />
</template>

<style scoped>
.stats-bar{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:24px;}
.stat-card-el{border-radius:10px;}

.section-card{border-radius:12px;margin-bottom:20px;}
.section-header{display:flex;justify-content:space-between;align-items:center;width:100%;}
.section-header h2{font-size:16px;font-weight:600;margin:0;}
.section-desc{font-size:13px;color:#888;margin-bottom:16px;}

/* 模型卡片 */
.model-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;}
.provider-card{border:2px solid #e5e7eb;border-radius:10px;cursor:pointer;transition:all .2s;position:relative;}
.provider-card:hover{border-color:#a5d6a7;box-shadow:0 2px 8px rgba(46,125,50,.1);}
.provider-card.active{border-color:#4D8088;background:#f1f8e9;}
.provider-left{display:flex;flex-direction:column;align-items:center;gap:4px;margin-bottom:8px;}
.provider-icon{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:16px;}
.provider-info{flex:1;}
.provider-name{font-size:14px;font-weight:600;display:flex;align-items:center;gap:8px;}
.provider-model{font-size:13px;color:#666;margin-top:2px;}
.provider-url{font-size:12px;color:#999;margin-top:2px;word-break:break-all;}
.provider-check{position:absolute;right:16px;top:16px;color:#4D8088;font-size:18px;font-weight:700;}
.provider-actions{display:flex;gap:6px;margin-top:12px;flex-wrap:wrap;padding-top:12px;border-top:1px solid #f0f0f0;}
.test-result{margin-top:8px;padding:6px 10px;border-radius:6px;font-size:12px;}
.test-result.ok{background:#EAF0F1;color:#4D8088;}
.test-result.err{background:#fbe9e7;color:#c62828;}

/* 参数 */
.params-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;}
.param-card{background:#fafafa;border:1px solid #eee;border-radius:8px;padding:12px;}
.param-card label{display:block;font-size:12px;color:#888;margin-bottom:6px;}

.global-params{margin-top:16px;padding-top:16px;border-top:1px solid #f0f0f0;}
.global-params h3{font-size:14px;font-weight:600;margin-bottom:16px;}
.slider-group{margin-bottom:20px;}
.slider-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;}
.slider-header label{font-size:13px;color:#555;}
.slider-value{font-size:13px;font-weight:600;}
.slider-range{display:flex;justify-content:space-between;font-size:11px;color:#aaa;margin-top:4px;}

/* 弹窗内 */
.form-row-2{display:grid;grid-template-columns:1fr 1fr;gap:12px;}
.field-hint{font-size:11px;color:#999;margin-top:4px;}

/* 获取模型 */
.fetch-models-bar{display:flex;align-items:center;gap:12px;margin-bottom:12px;}
.remote-models{max-height:200px;overflow-y:auto;border:1px solid #eee;border-radius:6px;margin-bottom:12px;}
.remote-model-item{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;cursor:pointer;font-size:13px;border-bottom:1px solid #f5f5f5;transition:background .15s;}
.remote-model-item:last-child{border-bottom:none;}
.remote-model-item:hover{background:#f5f5f5;}
.remote-model-item.selected{background:#EAF0F1;color:#4D8088;font-weight:500;}
</style>
