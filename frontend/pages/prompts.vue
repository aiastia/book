<script setup lang="ts">
import { API } from '~/composables/api'
useHead({ title: '提示词模板 — 墨语' })
const msg = useMessage()

const { data: templates, refresh: refresh } = await useFetch<any>(() => `/prompt-templates`)
const selectedId = ref<number | null>(null)
const versions = ref<any[]>([])
const activeVersion = ref<any>(null)
const showCreateVersion = ref(false)
const newVersionPrompt = ref('')
const creating = ref(false)

const categoryLabels: Record<string, string> = {
  custom: '自定义', chapter: '章节', outline: '大纲', character: '角色',
  world: '世界观', analysis: '分析', foreshadow: '伏笔', inspire: '灵感',
  skill: '写作技能', mcp: 'MCP', tool: '工具', other: '其他', import: '导入',
}

// 按分类分组
const grouped = computed(() => {
  const g: Record<string, any[]> = {}
  const order = ['chapter', 'outline', 'character', 'world', 'analysis', 'foreshadow', 'inspire', 'skill', 'mcp', 'tool', 'import', 'custom', 'other']
  for (const s of templates.value || []) {
    const cat = s.category || 'other'
    ;(g[cat] = g[cat] || []).push(s)
  }
  const sorted: Record<string, any[]> = {}
  for (const k of order) {
    if (g[k]) sorted[k] = g[k]
  }
  for (const k of Object.keys(g)) {
    if (!sorted[k]) sorted[k] = g[k]
  }
  return sorted
})

// 选中的模板
const selectedTemplate = computed(() => {
  if (!selectedId.value) return null
  return (templates.value || []).find((t: any) => t.id === selectedId.value)
})

// 加载模板版本
async function selectTemplate(id: number) {
  selectedId.value = id
  versions.value = []
  activeVersion.value = null
  try {
    const vers = await API.prompt.listVersions(id)
    versions.value = vers || []
    activeVersion.value = versions.value.find((v: any) => v.is_active) || versions.value[0] || null
  } catch {
    msg.error('加载版本失败')
  }
}

// 激活版本
async function activateVersion(v: any) {
  if (!selectedId.value) return
  try {
    await API.prompt.activateVersion(selectedId.value, v.id)
    activeVersion.value = v
    versions.value = versions.value.map((ver: any) => ({ ...ver, is_active: ver.id === v.id }))
    msg.success(`已切换到版本 v${v.version}`)
  } catch {
    msg.error('切换版本失败')
  }
}

// 打开创建新版本弹窗
function openCreateVersion() {
  newVersionPrompt.value = activeVersion.value?.system_prompt || ''
  showCreateVersion.value = true
}

// 创建新版本
async function onCreateVersion() {
  if (!selectedId.value || !newVersionPrompt.value.trim()) {
    msg.warning('请填写提示词内容')
    return
  }
  creating.value = true
  try {
    await API.prompt.createVersion(selectedId.value, {
      system_prompt: newVersionPrompt.value,
      user_prompt: '',
    })
    showCreateVersion.value = false
    msg.success('新版本已创建')
    await selectTemplate(selectedId.value)
  } catch {
    msg.error('创建版本失败')
  } finally {
    creating.value = false
  }
}

// 删除自定义模板
async function onDeleteTemplate(t: any) {
  if (!await msg.confirm('确认删除此自定义模板？此操作不可恢复。')) return
  try {
    await API.prompt.delete(t.id)
    if (selectedId.value === t.id) selectedId.value = null
    msg.success('已删除')
    await refresh()
  } catch {
    msg.error('删除失败')
  }
}

// 版本选择下拉
const versionOptions = computed(() =>
  versions.value.map((v: any) => ({
    value: v.id,
    label: `v${v.version}${v.is_active ? ' (当前)' : ''} — ${new Date(v.created_at).toLocaleDateString()}`,
  }))
)

function onVersionChange(vid: number) {
  const v = versions.value.find((ver: any) => ver.id === vid)
  if (v) activeVersion.value = v
}
</script>

<template>
  <PageHeader title="提示词模板" back="/books">
    <template #actions>
      <NuxtLink to="/skill-manage">
        <a-button>前往 Skill 管理 →</a-button>
      </NuxtLink>
    </template>
  </PageHeader>

  <div class="page-content">
    <p class="page-desc">提示词模板的版本管理和精细化调优。你可以基于默认模板创建自定义版本，切换激活版本。
      <br/><b>此页面负责</b>：版本管理、激活切换、版本对比（精细化调优）。
      <br/><b>Skill 开关</b>：如需开关 Skill 或安装新 Skill，请使用「Skill 管理」页面。
    </p>

    <div class="tpl-layout">
      <!-- 左侧：模板列表 -->
      <div class="tpl-sidebar">
        <div v-for="(items, cat) in grouped" :key="cat" class="tpl-category">
          <div class="tpl-cat-header">{{ categoryLabels[cat] || cat }}</div>
          <div
            v-for="t in items" :key="t.id"
            class="tpl-item"
            :class="{ active: selectedId === t.id }"
            @click="selectTemplate(t.id)"
          >
            <div class="tpl-item-name">{{ t.display_name || t.description || t.name }}</div>
            <a-tag v-if="t.is_system" size="small" color="default">系统</a-tag>
            <a-tag v-else size="small" color="warning">自定义</a-tag>
          </div>
        </div>
        <a-empty v-if="!templates || !templates.length" description="暂无模板" />
      </div>

      <!-- 右侧：模板详情 -->
      <div class="tpl-detail">
        <template v-if="selectedTemplate">
          <div class="tpl-detail-header">
            <div>
              <h2>{{ selectedTemplate.display_name || selectedTemplate.description || selectedTemplate.name }}</h2>
              <p class="tpl-detail-desc">{{ selectedTemplate.description || '暂无描述' }}</p>
            </div>
            <div class="tpl-detail-actions">
              <a-button type="primary" @click="openCreateVersion">基于当前版本创建新版本</a-button>
              <a-button v-if="!selectedTemplate.is_system" danger @click="onDeleteTemplate(selectedTemplate)">删除模板</a-button>
            </div>
          </div>

          <!-- 版本切换 -->
          <div v-if="versions.length" class="version-bar">
            <span class="version-label">版本：</span>
            <a-select :value="activeVersion?.id" @change="onVersionChange" style="width: 280px;">
              <a-select-option
                v-for="opt in versionOptions" :key="opt.value"
                :label="opt.label" :value="opt.value"
              />
            </a-select>
            <a-button
              v-if="activeVersion && !activeVersion.is_active"
              type="primary" size="small"
              @click="activateVersion(activeVersion)"
            >激活此版本</a-button>
            <a-tag v-if="activeVersion?.is_active" color="success" size="small">当前使用</a-tag>
          </div>

          <!-- 提示词内容 -->
          <div v-if="activeVersion" class="prompt-content">
            <div class="prompt-content-header">
              <span>提示词内容 (v{{ activeVersion.version }})</span>
              <a-tag size="small">{{ activeVersion.is_active ? '活跃版本' : '历史版本' }}</a-tag>
            </div>
            <a-textarea
              :value="activeVersion.system_prompt"
              :rows="20"
              readonly
              class="prompt-viewer"
            />
          </div>

          <a-empty v-else description="选择模板查看内容" />
        </template>

        <a-empty v-else description="← 从左侧选择一个模板查看详情" />
      </div>
    </div>
  </div>

  <!-- 创建新版本弹窗 -->
  <a-modal v-model:open="showCreateVersion" title="创建新版本" width="640px" :destroy-on-close="true">
    <p style="color:#888;font-size:13px;margin-bottom:12px;">编辑后保存为新版本，你可以随时在不同版本间切换。</p>
    <a-textarea
      v-model:value="newVersionPrompt"
      :rows="18"
      placeholder="输入提示词内容..."
    />
    <template #footer>
      <a-button @click="showCreateVersion = false">取消</a-button>
      <a-button type="primary" :loading="creating" @click="onCreateVersion">
        {{ creating ? '创建中...' : '创建版本' }}
      </a-button>
    </template>
  </a-modal>
</template>

<style scoped>
.page-desc{color:var(--color-fg-secondary);font-size:var(--text-sm);margin-bottom:16px;}
.tpl-layout{display:grid;grid-template-columns:260px 1fr;gap:20px;min-height:500px;}

/* 左侧列表 */
.tpl-sidebar{background:#fff;border:1px solid var(--color-border);border-radius:var(--radius-lg);overflow-y:auto;max-height:calc(100vh - 200px);}
.tpl-category{border-bottom:1px solid var(--color-border-light);}
.tpl-category:last-child{border-bottom:none;}
.tpl-cat-header{padding:10px 16px;font-size:var(--text-xs);font-weight:600;color:var(--color-fg-muted);background:var(--color-bg-page);}
.tpl-item{display:flex;justify-content:space-between;align-items:center;padding:10px 16px;cursor:pointer;transition:background .15s;border-left:3px solid transparent;}
.tpl-item:hover{background:#f5f5f5;}
.tpl-item.active{background:var(--color-accent-bg);border-left-color:var(--color-primary);}
.tpl-item-name{font-size:var(--text-sm);font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;margin-right:8px;}

/* 右侧详情 */
.tpl-detail{background:#fff;border:1px solid var(--color-border);border-radius:var(--radius-lg);padding:24px;overflow-y:auto;max-height:calc(100vh - 200px);}
.tpl-detail-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px;gap:16px;}
.tpl-detail-header h2{font-size:var(--text-xl);font-weight:600;margin:0 0 6px;}
.tpl-detail-desc{color:var(--color-fg-secondary);font-size:var(--text-sm);margin:0;}
.tpl-detail-actions{display:flex;gap:8px;flex-shrink:0;}

/* 版本栏 */
.version-bar{display:flex;align-items:center;gap:12px;margin-bottom:16px;padding:12px 16px;background:var(--color-bg-page);border-radius:var(--radius-md);}
.version-label{font-size:var(--text-sm);color:var(--color-fg-secondary);white-space:nowrap;}

/* 提示词内容 */
.prompt-content{border:1px solid var(--color-border-light);border-radius:var(--radius-md);overflow:hidden;}
.prompt-content-header{display:flex;justify-content:space-between;align-items:center;padding:10px 16px;background:var(--color-bg-page);font-size:var(--text-sm);font-weight:500;}
.prompt-viewer :deep(textarea){font-family:monospace;font-size:13px;line-height:1.6;}

@media(max-width:768px){.tpl-layout{grid-template-columns:1fr;}.tpl-sidebar{max-height:300px;}}
</style>
