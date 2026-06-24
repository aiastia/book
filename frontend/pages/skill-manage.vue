<script setup lang="ts">
import { useProjectApi } from '~/composables/useProjectApi'
useHead({ title: 'Skill 管理 — 墨语' })
const msg = useMessage()
const api = useProjectApi()
const { data: skills, refresh } = await api.listSkills()
const editing = ref<any>(null)
const editPrompt = ref('')
const showCreate = ref(false)
const createForm = reactive({
  name: '',
  display_name: '',
  description: '',
  category: 'custom',
  system_prompt: '',
})
const createFromMd = ref('')
const creating = ref(false)
const activeTab = ref<string>('form')

const categories = ['custom', 'chapter', 'outline', 'character', 'world', 'analysis', 'foreshadow', 'inspire', 'skill', 'mcp', 'tool']
const categoryLabels: Record<string, string> = {
  custom: '自定义', chapter: '章节', outline: '大纲', character: '角色',
  world: '世界观', analysis: '分析', foreshadow: '伏笔', inspire: '灵感',
  skill: '写作技能', mcp: 'MCP', tool: '工具', other: '其他', import: '导入',
}

async function onToggle(s: any) {
  try { await api.updateSkill(s.id, { is_enabled: !s.is_enabled }); await refresh() } catch (e: any) { msg.error('操作失败') }
}
async function onToggleCustom(s: any) {
  const newVal = !s.is_customized
  try { await api.updateSkill(s.id, { is_customized: newVal }); await refresh(); msg.success(newVal ? '已开启自定义' : '已恢复系统默认') } catch (e: any) { msg.error('操作失败') }
}
async function onAcceptSystem(s: any) {
  if (!await msg.confirm('确认用系统最新版本覆盖你的自定义版本？')) return
  try { await api.updateSkill(s.id, { system_prompt: s.system_prompt, is_customized: true }); await refresh(); msg.success('已更新为系统版本') } catch (e: any) { msg.error('更新失败') }
}
function openEdit(s: any) {
  editing.value = s
  editPrompt.value = s.is_customized ? (s.custom_prompt || s.system_prompt) : s.system_prompt
}
async function onSavePrompt() {
  try { await api.updateSkill(editing.value.id, { system_prompt: editPrompt.value }); editing.value = null; await refresh() } catch (e: any) { msg.error('保存失败') }
}
async function onReset(s: any) {
  if (!await msg.confirm('确认重置到系统默认？')) return
  try { await api.resetSkill(s.id); await refresh() } catch (e: any) { msg.error('重置失败') }
}
async function onResetAll() {
  if (!await msg.confirm('确认将所有提示词重置为系统默认版本？这将清除所有你自定义过的提示词，不可恢复。')) return
  try { await api.resetAllSkills(); await refresh(); msg.success('已全部重置') } catch (e: any) { msg.error('重置失败：' + formatError(e)) }
}
async function onDeleteCustom(s: any) {
  if (!await msg.confirm(`确认删除自定义 Skill「${s.display_name || s.name}」？此操作不可恢复。`)) return
  try { await api.deleteCustomSkill(s.id); await refresh() } catch (e: any) { msg.error('删除失败：' + formatError(e)) }
}

/** 解析 MD 内容为 Skill 创建参数 */
function parseMdToSkill(md: string) {
  const lines = md.split('\n')
  let name = ''
  let displayName = ''
  let description = ''
  let prompt = md

  // 尝试从 YAML frontmatter 解析元数据
  if (md.startsWith('---')) {
    const endIdx = md.indexOf('---', 3)
    if (endIdx > 0) {
      const frontmatter = md.slice(3, endIdx).trim()
      prompt = md.slice(endIdx + 3).trim()
      for (const line of frontmatter.split('\n')) {
        const m = line.match(/^(\w+):\s*(.+)/)
        if (m) {
          const [, key, val] = m
          if (key === 'name') name = val.trim()
          else if (key === 'display_name' || key === 'title') displayName = val.trim()
          else if (key === 'description' || key === 'desc') description = val.trim()
        }
      }
    }
  }

  // 如果没有 frontmatter，从标题解析
  if (!name) {
    const firstLine = lines[0] || ''
    const titleMatch = firstLine.match(/^#+\s*(.+)/)
    if (titleMatch) {
      name = titleMatch[1].trim()
      displayName = name
      prompt = lines.slice(1).join('\n').trim()
    } else {
      name = 'custom_skill_' + Date.now()
    }
  }

  return { name, display_name: displayName || name, description: description || `自定义 Skill: ${name}`, system_prompt: prompt }
}

async function onCreateFromForm() {
  if (!createForm.name.trim() || !createForm.system_prompt.trim()) {
    msg.warning('请填写 Skill 名称和提示词内容')
    return
  }
  creating.value = true
  try {
    await api.createSkill(createForm)
    showCreate.value = false
    Object.assign(createForm, { name: '', display_name: '', description: '', category: 'custom', system_prompt: '' })
    await refresh()
  } catch (e: any) { msg.error('创建失败：' + formatError(e)) }
  finally { creating.value = false }
}

async function onCreateFromMd() {
  if (!createFromMd.value.trim()) {
    msg.warning('请粘贴 MD 内容')
    return
  }
  creating.value = true
  try {
    const parsed = parseMdToSkill(createFromMd.value)
    await api.createSkill(parsed)
    showCreate.value = false
    createFromMd.value = ''
    await refresh()
  } catch (e: any) { msg.error('创建失败：' + formatError(e)) }
  finally { creating.value = false }
}

function openCreate() {
  showCreate.value = true
  activeTab.value = 'form'
  createFromMd.value = ''
  Object.assign(createForm, { name: '', display_name: '', description: '', category: 'custom', system_prompt: '' })
}

const grouped = computed(() => {
  const g: Record<string, any[]> = {}
  for (const s of skills.value || []) {
    const cat = s.category || 'other'
    ;(g[cat] = g[cat] || []).push(s)
  }
  return g
})
</script>
<template>
  <PageHeader title="Skill 管理">
    <template #actions>
      <a-button type="primary" @click="openCreate">+ 安装 Skill</a-button>
      <a-button danger @click="onResetAll">重置全部为系统默认</a-button>
    </template>
  </PageHeader>
  <div class="page-content">
    <p style="color:#888;font-size:13px;margin-bottom:16px;">
      Skill 是 AI 生成各类型内容的提示词模板。可开关、自定义编辑、通过 MD 文档安装新 Skill。
      <br/><b>此页面负责</b>：Skill 的开关、基础编辑、安装、重置（日常运维）。
      <br/><b>提示词调优</b>：如需版本管理和精细化调优，请使用「提示词」页面。
    </p>

    <!-- 按分类展示 -->
    <div v-for="(items, cat) in grouped" :key="cat" class="skill-section">
      <h3 class="skill-cat-title">
        {{ categoryLabels[cat] || cat }}
        <a-tag size="small" color="success">{{ items.length }}</a-tag>
      </h3>
      <div class="skill-list">
        <a-card
          v-for="s in items" :key="s.id"
          hoverable
          class="skill-card"
          :class="{ disabled: !s.is_enabled, customized: s.is_customized }"
        >
          <div class="skill-head">
            <div>
              <div class="skill-name">
                {{ s.display_name || s.name }}
                <a-tag v-if="s.is_customized" color="purple" size="small" style="margin-left:4px;">已自定义</a-tag>
                <a-tag v-if="s.system_updated" color="orange" size="small" style="margin-left:4px;">系统已更新</a-tag>
              </div>
              <a-tag
                :color="s.skill_type === 'custom' ? 'warning' : 'default'"
                size="small"
                style="margin-top:4px;"
              >
                {{ s.skill_type === 'custom' ? '自定义' : (categoryLabels[s.category] || s.category) }}
              </a-tag>
            </div>
            <a-switch :checked="s.is_enabled" @change="onToggle(s)" />
          </div>
          <div class="skill-desc">{{ s.description || '暂无描述' }}</div>
          <div v-if="s.system_prompt" class="skill-prompt" @click="openEdit(s)" :title="'点击查看完整提示词（' + (s.is_customized ? (s.custom_prompt || s.system_prompt) : s.system_prompt).length + '字）'">{{ (s.is_customized ? (s.custom_prompt || s.system_prompt) : s.system_prompt).slice(0, 300) }}{{ (s.is_customized ? (s.custom_prompt || s.system_prompt) : s.system_prompt).length > 300 ? '... (点击查看全文)' : '' }}</div>
          <!-- 自定义开关 -->
          <div class="skill-custom-row">
            <span style="font-size:12px;color:#888;">自定义提示词</span>
            <a-switch :checked="s.is_customized" size="small" @change="onToggleCustom(s)" />
          </div>
          <div class="skill-actions">
            <a-button size="small" @click="openEdit(s)" :disabled="!s.is_customized && s.skill_type !== 'custom'">编辑提示词</a-button>
            <a-button v-if="s.system_updated" size="small" type="primary" @click="onAcceptSystem(s)">更新为系统版本</a-button>
            <a-button v-if="s.is_customized" size="small" @click="onReset(s)">重置默认</a-button>
            <a-button v-if="s.skill_type === 'custom'" size="small" danger @click="onDeleteCustom(s)">删除</a-button>
          </div>
        </a-card>
      </div>
    </div>
    <a-empty v-if="!skills || !skills.length" description="暂无 Skill，点击右上角「安装 Skill」添加" :image-style="{ height: '80px' }" />
  </div>

  <!-- 编辑提示词弹窗 -->
  <a-modal
    v-model:open="editing"
    :title="'编辑提示词 — ' + (editing?.display_name || editing?.name || '')"
    width="640px"
    :mask-closable="false"
  >
    <a-textarea
      v-model:value="editPrompt"
      :rows="16"
      placeholder="输入 system prompt 内容..."
      style="font-family:monospace;"
    />
    <template #footer>
      <a-button @click="editing = null">取消</a-button>
      <a-button type="primary" @click="onSavePrompt">保存</a-button>
    </template>
  </a-modal>

  <!-- 安装 Skill 弹窗 -->
  <a-modal
    v-model:open="showCreate"
    title="安装新 Skill"
    width="640px"
    :mask-closable="false"
  >
    <a-tabs v-model:activeKey="activeTab">
      <a-tab-pane key="form" tab="表单创建">
        <a-form layout="vertical">
          <a-form-item label="Skill 名称 *" required>
            <a-input v-model:value="createForm.name" placeholder="例如：my_custom_skill" />
          </a-form-item>
          <a-form-item label="显示名称">
            <a-input v-model:value="createForm.display_name" placeholder="例如：我的自定义 Skill" />
          </a-form-item>
          <a-form-item label="描述">
            <a-input v-model:value="createForm.description" placeholder="简要描述此 Skill 的用途" />
          </a-form-item>
          <a-form-item label="分类">
            <a-select v-model:value="createForm.category" style="width:100%;">
              <a-select-option v-for="c in categories" :key="c" :label="categoryLabels[c] || c" :value="c" />
            </a-select>
          </a-form-item>
          <a-form-item label="提示词内容 *" required>
            <a-textarea
              v-model:value="createForm.system_prompt"
              :rows="10"
              placeholder="输入 system prompt 内容..."
              style="font-family:monospace;"
            />
          </a-form-item>
        </a-form>
      </a-tab-pane>

      <a-tab-pane key="md" tab="从 MD 安装">
        <a-alert
          type="info"
          :closable="false"
          style="margin-bottom:12px;"
        >
          <template #message>
            <span style="font-size:12px;line-height:1.6;">
              粘贴 Markdown 格式的 Skill 内容。支持 YAML frontmatter：<code style="background:#e8e8e8;padding:1px 4px;border-radius:3px;">---</code> 开头，可包含 <code style="background:#e8e8e8;padding:1px 4px;border-radius:3px;">name</code>、<code style="background:#e8e8e8;padding:1px 4px;border-radius:3px;">display_name</code>、<code style="background:#e8e8e8;padding:1px 4px;border-radius:3px;">description</code> 字段。其余内容将作为提示词。
            </span>
          </template>
        </a-alert>
        <a-textarea
          v-model:value="createFromMd"
          :rows="14"
          placeholder="---
name: my_skill
display_name: 我的Skill
description: 描述
---

你的提示词内容..."
          style="font-family:monospace;"
        />
      </a-tab-pane>
    </a-tabs>

    <template #footer>
      <a-button @click="showCreate = false">取消</a-button>
      <a-button type="primary" :loading="creating" @click="activeTab === 'form' ? onCreateFromForm() : onCreateFromMd()">
        创建 Skill
      </a-button>
    </template>
  </a-modal>
</template>
<style scoped>
.skill-section{margin-bottom:28px;}
.skill-cat-title{font-size:14px;font-weight:600;color:#555;margin-bottom:12px;display:flex;align-items:center;gap:8px;}
.skill-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px;}
.skill-card{transition:all .2s;}
.skill-card.disabled{opacity:.6;}
.skill-card.customized{border-left:3px solid #722ED1;}
.skill-custom-row{display:flex;align-items:center;justify-content:space-between;margin-top:8px;padding-top:8px;border-top:1px dashed #E8E4DC;}
.skill-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;}
.skill-name{font-size:15px;font-weight:600;margin-bottom:4px;}
.skill-desc{font-size:13px;color:#888;margin-bottom:8px;line-height:1.5;}
.skill-prompt{font-size:12px;color:#aaa;background:#f9f9f9;padding:8px;border-radius:4px;margin-bottom:8px;font-family:monospace;line-height:1.4;max-height:120px;overflow:hidden;cursor:pointer;}
.skill-actions{display:flex;gap:8px;}
</style>
