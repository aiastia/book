<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { API } from '~/composables/api'
import { useProject } from '~/composables/useProject'
import { apiGet } from '~/composables/useApi'

const { currentProjectId } = useProject()
const msg = useMessage()

const modes = ref<Record<string, any>>({})
const loading = ref(false)
const saving = ref(false)

// 测试状态
const testingMode = ref<string | null>(null)
const testResults = ref<Record<string, string>>({})

const modeGroups = [
  { key: 'world',     label: '🌍 生成世界观',        desc: '世界设定生成' },
  { key: 'character', label: '👤 生成人物设定',      desc: '角色创建与批量生成' },
  { key: 'outline',   label: '📋 生成剧情大纲',      desc: '大纲/续写' },
  { key: 'expand',    label: '📑 每章剧情规划',      desc: '大纲展开为子章节' },
  { key: 'chapter',   label: '✍️ 正文写作',          desc: '章节生成 (1-1/1-N)' },
  { key: 'polish',    label: '✨ 章节润色',          desc: '去AI味' },
  { key: 'analysis',  label: '🔍 一致性检查/分析',   desc: '剧情分析' },
]

const effortOptions = [
  { value: 'high', label: '高思考' },
  { value: 'medium', label: '中思考' },
  { value: 'low', label: '低思考' },
  { value: 'none', label: '关闭思考' },
]

// 模式分组 → 技能 key 映射（与后端 _SKILL_TO_THINKING_MODE 一致）
const modeKeyMap: Record<string, string> = {
  world: 'world_core_generate',
  character: 'character_generate',
  outline: 'outline_create',
  expand: 'outline_expand_single',
  chapter: 'chapter_generation_',
  polish: 'ai_denoising',
  analysis: 'plot_analysis',
}

async function load() {
  loading.value = true
  try {
    let pid = currentProjectId.value
    if (!pid) {
      const projects = await API.book.list()
      if (!projects?.length) {
        modes.value = {}
        return
      }
      pid = projects[0].id
    }
    const data = await apiGet<any>(`/api/projects/${pid}/thinking-modes`)
    modes.value = data?.modes || {}
  } catch (e: any) {
    modes.value = {}
  } finally { loading.value = false }
}
async function save() {
  if (!currentProjectId.value && !Object.keys(modes.value).length) return
  saving.value = true
  try {
    let pid = currentProjectId.value
    if (!pid) {
      const projects = await API.book.list()
      if (!projects?.length) { msg.warning('请先创建一个项目'); return }
      pid = projects[0].id
    }
    await API.book.saveThinkingModes(modes.value, pid)
    msg.success('已保存')
  } catch (e: any) { msg.error('保存失败') }
  finally { saving.value = false }
}

async function onTestMode(key: string) {
  testingMode.value = key
  testResults.value[key] = ''
  try {
    // 获取项目 ID：优先用当前项目，否则取用户第一个项目
    let pid = currentProjectId.value
    if (!pid) {
      const projects = await API.book.list()
      if (!projects?.length) {
        testResults.value[key] = '❌ 请先创建一个项目再测试'
        return
      }
      pid = projects[0].id
    }
    const r = await API.book.testThinkingMode(modeKeyMap[key] || key, pid)
    const cfg = r.mode_config || {}
    const enabled = cfg.enabled
    const parts: string[] = []
    if (enabled) {
      parts.push(`🧠 思考已开启`)
      parts.push(`effort=${cfg.reasoning_effort || '默认'}`)
    } else {
      parts.push(`🧢 思考已关闭`)
    }
    if (r.result.thinking_active) {
      parts.push(`⚠️ 推理实际运行中`)
      parts.push(`reasoning_tokens=${r.result.reasoning_tokens}`)
    } else {
      parts.push(`✅ 推理未运行`)
    }
    parts.push(`回复：${r.result.reply}`)
    testResults.value[key] = parts.join(' | ')
    // 后端返回的警告（如关闭思考但模型仍在推理）
    if (r.warning) {
      testResults.value[key] += ` | ⚡ ${r.warning}`
    }
  } catch (e: any) {
    const detail = e?.data?.detail || ''
    testResults.value[key] = `❌ 测试失败：${detail || e?.message || '未知错误'}`
  } finally {
    testingMode.value = null
  }
}

function toggleMode(key: string) {
  if (!modes.value[key]) modes.value[key] = { enabled: false, reasoning_effort: 'low', temperature: null }
  modes.value[key].enabled = !modes.value[key].enabled
}

onMounted(load)
</script>

<template>
  <a-card title="🧠 思考模式设置" size="small" :loading="loading" style="margin-top:16px">
    <template #extra>
      <a-button type="primary" size="small" :loading="saving" @click="save">保存</a-button>
    </template>

    <a-row :gutter="[8, 8]">
      <a-col :span="12" v-for="g in modeGroups" :key="g.key">
        <a-card size="small" :class="{ 'mode-card-on': modes[g.key]?.enabled, 'mode-card-off': !modes[g.key]?.enabled }">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
            <span style="font-weight:600;font-size:13px">{{ g.label }}</span>
            <div style="display:flex;align-items:center;gap:6px">
              <a-button size="small" :loading="testingMode===g.key" @click="onTestMode(g.key)">
                {{ testingMode === g.key ? '测试中...' : '🧪 测试' }}
              </a-button>
              <a-switch size="small" :checked="!!modes[g.key]?.enabled" @change="toggleMode(g.key)" />
            </div>
          </div>
          <div style="font-size:11px;color:#8c8c8c;margin-bottom:6px">{{ g.desc }}</div>
          <template v-if="modes[g.key]?.enabled">
            <div style="display:flex;gap:8px;align-items:center">
              <span style="font-size:11px">思考深度：</span>
              <a-select v-model:value="modes[g.key].reasoning_effort" size="small" style="width:100px">
                <a-select-option v-for="eo in effortOptions" :key="eo.value" :value="eo.value">{{ eo.label }}</a-select-option>
              </a-select>
              <a-tooltip title="实际 temperature = 输入值 ÷ 100，例如 100 = 1.0">
                <span style="font-size:11px;margin-left:8px;cursor:help;border-bottom:1px dashed #8c8c8c">温度：</span>
              </a-tooltip>
              <a-input-number v-model:value="modes[g.key].temperature" size="small" :min="0" :max="200" :step="5" style="width:70px" placeholder="默认" />
            </div>
          </template>
          <div v-if="testResults[g.key]" class="test-result" :class="{ ok: testResults[g.key].startsWith('✅'), err: testResults[g.key].startsWith('❌'), warn: testResults[g.key].includes('⚠️') }">
            {{ testResults[g.key] }}
          </div>
        </a-card>
      </a-col>
    </a-row>
  </a-card>
</template>

<style scoped>
.mode-card-on  { border: 1px solid #597ef7; background: #f0f5ff; }
.mode-card-off { border: 1px solid #e8e4d9; background: #fafaf7; opacity: 0.7; }
.test-result { margin-top: 6px; padding: 4px 8px; border-radius: 4px; font-size: 11px; }
.test-result.ok { background: #EAF0F1; color: #4D8088; }
.test-result.err { background: #fbe9e7; color: #c62828; }
.test-result.warn { background: #fff3e0; color: #e65100; }
</style>
