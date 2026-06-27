<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useProjectApi } from '~/composables/useProjectApi'
import { useProject } from '~/composables/useProject'
import { apiGet } from '~/composables/useApi'

const api = useProjectApi()
const { currentProjectId } = useProject()
const msg = useMessage()

const modes = ref<Record<string, any>>({})
const loading = ref(false)
const saving = ref(false)

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

async function load() {
  if (!currentProjectId.value) return
  loading.value = true
  try {
    const data = await apiGet<any>(`/api/projects/${currentProjectId.value}/thinking-modes`)
    modes.value = data?.modes || {}
  } catch { /* 暂无数据 */ }
  finally { loading.value = false }
}
async function save() {
  if (!currentProjectId.value) return
  saving.value = true
  try {
    await api.saveThinkingModes(modes.value)
    msg.success('已保存')
  } catch (e: any) { msg.error('保存失败') }
  finally { saving.value = false }
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
            <a-switch size="small" :checked="!!modes[g.key]?.enabled" @change="toggleMode(g.key)" />
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
        </a-card>
      </a-col>
    </a-row>
  </a-card>
</template>

<style scoped>
.mode-card-on  { border: 1px solid #597ef7; background: #f0f5ff; }
.mode-card-off { border: 1px solid #e8e4d9; background: #fafaf7; opacity: 0.7; }
</style>
