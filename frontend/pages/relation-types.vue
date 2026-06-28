<script setup lang="ts">
// 关系类型管理：增删改查项目中已用的关系类型
import { API } from '~/composables/api'
import { useProject } from '~/composables/useProject'
import type { RelationType } from '~/composables/api/types'
useHead({ title: '关系类型管理 — 墨语' })
const { currentProjectId, projectUrl } = useProject()
if (!currentProjectId.value) await navigateTo('/books')

const msg = useMessage()
const { data: types, refresh: refresh } = await useFetch<RelationType[]>(() => `/api/projects/${currentProjectId.value}/relations/types`)

// 颜色池
const typeColors = ['#e91e63','#ff5722','#f44336','#2196f3','#6B9CA4','#4caf50','#ff9800','#9c27b0','#00bcd4','#795548']
const typeColorMap = ref<Record<string, string>>({})
function colorFor(name: string): string {
  if (!typeColorMap.value[name]) {
    const idx = Object.keys(typeColorMap.value).length % typeColors.length
    typeColorMap.value[name] = typeColors[idx]
  }
  return typeColorMap.value[name]
}

// 新增
const showAdd = ref(false)
const newTypeName = ref('')
const newTypeCategory = ref('social')
const categoryOptions = [
  { key: 'family', label: '亲情' },
  { key: 'romantic', label: '情感' },
  { key: 'hostile', label: '敌对' },
  { key: 'professional', label: '职业' },
  { key: 'social', label: '社交' },
]

async function onAdd() {
  const name = newTypeName.value.trim()
  if (!name) { msg.warning('请输入类型名称'); return }
  try {
    await API.relation.create({ from_character_id: 0, to_character_id: 0, relation_type: name, category: newTypeCategory.value, intimacy: 0, status: 'template' })
    newTypeName.value = ''
    newTypeCategory.value = 'social'
    showAdd.value = false
    await refresh()
    msg.success(`已添加「${name}」`)
  } catch (e: any) { msg.error('添加失败：' + formatError(e)) }
}

// 重命名
const renaming = ref<string | null>(null)
const renameTarget = ref('')

function openRename(t: any) {
  renaming.value = t.name
  renameTarget.value = t.name
}
async function onRename() {
  const oldName = renaming.value
  const newName = renameTarget.value.trim()
  if (!oldName || !newName || oldName === newName) { renaming.value = null; return }
  try {
    const res = await API.relation.renameType({ old: oldName, new: newName })
    renaming.value = null
    await refresh()
    msg.success(`已重命名「${oldName}」→「${newName}」（${(res as any).updated || 0} 条关系已更新）`)
  } catch (e: any) { msg.error('重命名失败：' + formatError(e)) }
}
function cancelRename() { renaming.value = null }

// 删除
async function onDeleteType(t: any) {
  // 排除占位模板
  if (t.count === 0 || t.name === 'template') {
    try { await API.relation.deleteType(t.name); await refresh(); msg.success(`已删除「${t.name}」`) }
    catch (e: any) { msg.error('删除失败：' + formatError(e)) }
    return
  }
  if (!await msg.confirm(`确定删除「${t.name}」？${t.count} 条关系将被改为"相识"。`)) return
  try {
    await API.relation.deleteType(t.name)
    await refresh()
    msg.success(`已删除「${t.name}」（${t.count} 条关系已改为相识）`)
  } catch (e: any) { msg.error('删除失败：' + formatError(e)) }
}
</script>

<template>
  <PageHeader title="🏷️ 关系类型管理">
    <template #actions>
      <NuxtLink :to="projectUrl('/relations')"><a-button>← 返回关系图谱</a-button></NuxtLink>
      <a-button type="primary" @click="showAdd = true">＋ 添加类型</a-button>
    </template>
  </PageHeader>

  <div class="page-content">
    <a-alert message="这里管理项目中所有的关系类型（如「同伴」「宿敌」「师徒」），重命名会批量更新所有使用该类型的关系记录。" type="info" show-icon style="margin-bottom:16px;" />

    <div v-if="(types || []).length" class="types-grid">
      <a-card v-for="t in types.filter((x:any) => x.name !== 'template')" :key="t.name" size="small" hoverable class="type-card">
        <template #title>
          <div style="display:flex;align-items:center;gap:8px;">
            <span class="type-dot" :style="{ background: colorFor(t.name) }"></span>
            <template v-if="renaming === t.name">
              <a-input v-model:value="renameTarget" size="small" style="width:120px;" @press-enter="onRename" />
              <a-button size="small" type="primary" @click="onRename">确定</a-button>
              <a-button size="small" @click="cancelRename">取消</a-button>
            </template>
            <template v-else>
              <span class="type-name">{{ t.name }}</span>
            </template>
          </div>
        </template>
        <div class="type-body">
          <span class="type-count">{{ t.count }} 条关系</span>
          <a-tag v-if="t.category" size="small" :color="{family:'pink',romantic:'orange',hostile:'red',professional:'blue',social:'cyan'}[t.category]||'default'">{{ {family:'亲情',romantic:'情感',hostile:'敌对',professional:'职业',social:'社交'}[t.category] || t.category }}</a-tag>
        </div>
        <template #actions>
          <a-button size="small" @click="openRename(t)">✏️ 重命名</a-button>
          <a-button size="small" danger @click="onDeleteType(t)">🗑 删除</a-button>
        </template>
      </a-card>
    </div>
    <a-empty v-else description="暂无关系类型，先生成角色和关系吧" />

    <!-- 新增弹窗 -->
    <a-modal v-model:open="showAdd" title="添加关系类型" width="400px" @ok="onAdd">
      <a-form-item label="类型名称">
        <a-input v-model:value="newTypeName" placeholder="如：难友、青梅竹马" @press-enter="onAdd" />
      </a-form-item>
      <a-form-item label="所属分类">
        <a-select v-model:value="newTypeCategory">
          <a-select-option v-for="o in categoryOptions" :key="o.key" :value="o.key">{{ o.label }}</a-select-option>
        </a-select>
      </a-form-item>
    </a-modal>
  </div>
</template>

<style scoped>
.types-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:14px; }
.type-card { border-radius:10px; }
.type-dot { width:12px; height:12px; border-radius:50%; flex-shrink:0; }
.type-name { font-size:15px; font-weight:600; }
.type-body { display:flex; align-items:center; justify-content:space-between; }
.type-count { color:#888; font-size:12px; }
</style>
