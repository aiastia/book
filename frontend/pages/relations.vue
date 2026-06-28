<script setup lang="ts">
// 角色关系：Vue Flow 图谱视图 + 表格视图 + 手动增删改（#17 增强）
// Vue Flow 提供拖拽/缩放/自动布局，对标 MuMuAINovel ReactFlow
import { VueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import { API } from '~/composables/api'
import { useProject } from '~/composables/useProject'
import type { Character, RelationType } from '~/composables/api/types'
useHead({ title: '角色关系 — 墨语' })
const { currentProjectId, projectUrl } = useProject()
if (!currentProjectId.value) await navigateTo('/books')

const msg = useMessage()
const { data: graph, refresh: refreshGraph } = await useFetch<any>(() => `/projects/${currentProjectId.value}/relations/graph`)
const { data: characters, refresh: refresh } = await useFetch<Character[]>(() => `/projects/${currentProjectId.value}/characters`)
// 全量关系列表（含 id，供表格编辑/删除用）
const relationsData = ref<any[]>([])
async function loadRelations() {
  const res = await API.relation.list()
  // useApi 返回 AsyncData，其 data 是 Ref
  const d = (res as any)?.data
  relationsData.value = (d?.value ?? d ?? []) as any[]
}
await loadRelations()

// 视图切换
const viewMode = ref<'chart' | 'table' | 'change_log' | 'manage_types'>('chart')

// 关系类型 → 颜色
const categoryColor: Record<string, string> = {
  family: '#e91e63', romantic: '#ff5722', hostile: '#f44336',
  professional: '#2196f3', social: '#6B9CA4',
}
const categoryLabel: Record<string, string> = {
  family: '亲情', romantic: '情感', hostile: '敌对',
  professional: '职业', social: '社交',
}

// ===== 表单：添加/编辑关系 =====
const showForm = ref(false)
const editing = ref<any>(null)
const form = reactive({
  from_character_id: null as number | null,
  to_character_id: null as number | null,
  relation_type: '',
  category: 'social' as string,
  intimacy: 0,
  status: 'active' as string,
  description: '',
})
const commonRelationTypes = ['同伴', '师徒', '恋人', '父子', '母女', '兄弟', '姐妹', '宿敌', '敌对', '同门', '上下级', '雇佣', '救命恩人', '青梅竹马', '挚友', '难友']

function openAdd() {
  editing.value = null
  Object.assign(form, {
    from_character_id: null,
    to_character_id: null,
    relation_type: '',
    category: 'social',
    intimacy: 0,
    status: 'active',
    description: '',
  })
  showForm.value = true
}

function openEdit(r: any) {
  editing.value = r  // r has id, from_character_id, to_character_id, relation_type, category, intimacy, status, description
  Object.assign(form, {
    from_character_id: r.from_character_id ?? null,
    to_character_id: r.to_character_id ?? null,
    relation_type: r.relation_type || '',
    category: r.category || 'social',
    intimacy: r.intimacy ?? 0,
    status: r.status || 'active',
    description: r.description || '',
  })
  showForm.value = true
}

async function onSave() {
  if (!form.from_character_id || !form.to_character_id) { msg.warning('请选择角色 A 和角色 B'); return }
  if (!form.relation_type.trim()) { msg.warning('请输入关系类型'); return }
  try {
    const body: any = { ...form }
    if (editing.value) {
      await API.relation.update(editing.value.id, body)
    } else {
      await API.relation.create(body)
    }
    showForm.value = false
    await refresh()
    await loadRelations()
    msg.success(editing.value ? '已更新' : '已添加')
  } catch (e: any) {
    msg.error('保存失败：' + formatError(e))
  }
}

// ===== 删除关系 =====
async function onDelete(record: any) {
  if (!await msg.confirm('确认删除此关系？')) return
  try {
    await API.relation.delete(record.id)
    await refresh()
    await loadRelations()
    msg.success('已删除')
  } catch (e: any) {
    msg.error('删除失败：' + formatError(e))
  }
}

// ===== 关系类型管理（子视图） =====
const { data: relationTypes, refresh: refreshTypes } = await useFetch<RelationType[]>(() => `/projects/${currentProjectId.value}/relations/types`)
const showAddType = ref(false)
const newTypeName = ref('')
const newTypeCategory = ref('social')
const renamingType = ref<string | null>(null)
const renameTarget = ref('')
const editCategory = ref('social')
const typeColors2 = ['#e91e63','#ff5722','#f44336','#2196f3','#6B9CA4','#4caf50','#ff9800','#9c27b0','#00bcd4','#795548']
const typeColorMap2 = ref<Record<string, string>>({})
function colorForType(name: string): string {
  if (!typeColorMap2.value[name]) {
    const idx = Object.keys(typeColorMap2.value).length % typeColors2.length
    typeColorMap2.value[name] = typeColors2[idx]
  }
  return typeColorMap2.value[name]
}
async function onAddType() {
  const name = newTypeName.value.trim()
  if (!name) { msg.warning('请输入类型名称'); return }
  try {
    await API.relation.create({ from_character_id: 0, to_character_id: 0, relation_type: name, category: newTypeCategory.value, intimacy: 0, status: 'template' })
    newTypeName.value = ''; newTypeCategory.value = 'social'; showAddType.value = false
    await refreshTypes(); await refresh()
    msg.success(`已添加「${name}」`)
  } catch (e: any) { msg.error('添加失败：' + formatError(e)) }
}
function openRenameType(t: any) { renamingType.value = t.name; renameTarget.value = t.name; editCategory.value = t.category || 'social' }
async function onRenameType() {
  const oldName = renamingType.value; const newName = renameTarget.value.trim()
  if (!oldName || !newName) { msg.warning('名称不能为空'); return }
  try {
    if (oldName !== newName) {
      await API.relation.renameType({ old: oldName, new: newName })
    }
    renamingType.value = null; await refreshTypes(); await refresh()
    msg.success(oldName !== newName ? `已重命名「${oldName}」→「${newName}」` : '已保存')
  } catch (e: any) { msg.error('更新失败：' + formatError(e)) }
}
async function onDeleteTypeItem(t: any) {
  if (!await msg.confirm(`确定删除「${t.name}」？${t.count || 0} 条关系将被改为"相识"。`)) return
  try { await API.relation.deleteType(t.name); await refreshTypes(); await refresh(); msg.success(`已删除「${t.name}」`) }
  catch (e: any) { msg.error('删除失败：' + formatError(e)) }
}

// ===== 关系变化日志（全量汇总） =====
const allChangeLogs = ref<any[]>([])
const loadingLogs = ref(false)
async function loadAllChangeLogs() {
  if (!relationsData.value?.length) { allChangeLogs.value = []; return }
  loadingLogs.value = true
  try {
    const results: any[] = []
    for (const r of relationsData.value) {
      if (!r.id) continue
      try {
        const res = await API.relation.getChangeLogs(r.id)
        const d = (res as any)?.data
        const logs = (d?.value ?? d ?? []) as any[]
        for (const log of logs) {
          results.push({
            ...log,
            char_a: r.char_a || r.from_name || `#${r.from_character_id}`,
            char_b: r.char_b || r.to_name || `#${r.to_character_id}`,
            relation_type: r.relation_type || '',
          })
        }
      } catch { /* skip */ }
    }
    results.sort((a, b) => (a.chapter_number || 0) - (b.chapter_number || 0) || a.id - b.id)
    allChangeLogs.value = results
  } finally {
    loadingLogs.value = false
  }
}

const logColumns = [
  { title: '章节', dataIndex: 'chapter_number', key: 'chapter_number', width: 80 },
  { title: '角色对', key: 'pair', width: 160 },
  { title: '变更详情', key: 'changes', width: 240 },
  { title: '摘要', dataIndex: 'summary', key: 'summary' },
  { title: '操作', key: 'actions', width: 60 },
]

// 格式化 changed_fields 为可读文本
function formatChanges(fields: Record<string, any>): string {
  if (!fields || !Object.keys(fields).length) return '—'
  const parts: string[] = []
  for (const [k, v] of Object.entries(fields)) {
    if (k === 'intimacy' && typeof v === 'object' && v.old !== undefined && v.new !== undefined) {
      parts.push(`亲密度 ${v.old} → ${v.new}`)
    } else if (k === 'relation_type') {
      parts.push(`关系类型 → ${v}`)
    } else {
      parts.push(`${k}: ${JSON.stringify(v)}`)
    }
  }
  return parts.join('；')
}

async function onDeleteLog(logId: number, relationId: number) {
  if (!await msg.confirm('确认删除此变化记录？')) return
  try {
    await API.relation.deleteChangeLog(relationId, logId)
    await loadAllChangeLogs()
    msg.success('已删除')
  } catch (e: any) {
    msg.error('删除失败：' + formatError(e))
  }
}

// 切换 tab 时加载日志
watch(viewMode, (v) => {
  if (v === 'change_log') loadAllChangeLogs()
})

// ===== 已用关系类型（从 edges 提取去重） =====
const usedRelationTypes = computed(() => {
  const edges = graph.value?.edges || []
  const types = new Map<string, number>()
  for (const e of edges) {
    const t = e.relation_type
    if (t) types.set(t, (types.get(t) || 0) + 1)
  }
  return Array.from(types.entries()).sort((a, b) => b[1] - a[1])
})

// ===== Vue Flow 节点/边 =====
const vfNodes = ref<any[]>([])
const vfEdges = ref<any[]>([])

function buildGraph() {
  if (!graph.value) return
  const ns = graph.value.nodes || []
  const es = graph.value.edges || []
  // 圆形布局作为初始位置（用户可拖拽调整）
  const cx = 400, cy = 300, r = 200
  vfNodes.value = ns.map((n: any, i: number) => {
    const isMain = n.role === '主角'
    const angle = (2 * Math.PI * i) / Math.max(ns.length, 1) - Math.PI / 2
    return {
      id: String(n.id),
      position: { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) },
      data: { label: n.name, role: n.role, isMain },
      type: 'character',
      style: {
        background: isMain ? '#4D8088' : '#5A9098',
        color: '#fff',
        border: 'none',
        borderRadius: '50%',
        width: '70px',
        height: '70px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: '13px',
        fontWeight: isMain ? '700' : '500',
        textAlign: 'center' as const,
      },
    }
  })
  vfEdges.value = es.map((e: any, i: number) => {
    const color = categoryColor[e.category] || '#999'
    return {
      id: `e${i}`,
      source: String(e.source),
      target: String(e.target),
      label: e.relation_type,
      animated: Math.abs(e.intimacy) > 50,
      style: { stroke: color, strokeWidth: Math.abs(e.intimacy) > 50 ? 2.5 : 1.5 },
      labelStyle: { fill: color, fontSize: 11, fontWeight: 600 },
      labelBgStyle: { fill: '#fff' },
      type: e.intimacy < 0 ? 'step' : 'default',
    }
  })
}
watch(graph, buildGraph, { immediate: true })

// 自动布局（简单的力导向 - 居中分布）
function autoLayout() {
  buildGraph()
  msg.info('已重置布局，可拖拽节点调整位置')
}

// 表格视图数据（使用 relationsData 列表，含 id 支持编辑/删除）
const tableData = computed(() => {
  if (!relationsData.value?.length) return []
  const nameMap = new Map<number, string>()
  ;(graph.value?.nodes || []).forEach((n: any) => nameMap.set(n.id, n.name))
  return relationsData.value.map((r: any) => ({
    id: r.id,
    char_a: r.from_name || nameMap.get(r.from_character_id) || `#${r.from_character_id}`,
    char_b: r.to_name || nameMap.get(r.to_character_id) || `#${r.to_character_id}`,
    relation_type: r.relation_type,
    category: r.category,
    category_label: categoryLabel[r.category] || '其他',
    intimacy: r.intimacy,
    status: r.status || 'active',
    from_character_id: r.from_character_id,
    to_character_id: r.to_character_id,
    description: r.description || '',
  }))
})
const tableColumns = [
  { title: '角色 A', dataIndex: 'char_a', key: 'char_a', width: 120 },
  { title: '关系', dataIndex: 'relation_type', key: 'relation_type', width: 120 },
  { title: '角色 B', dataIndex: 'char_b', key: 'char_b', width: 120 },
  { title: '分类', dataIndex: 'category_label', key: 'category_label', width: 100 },
  { title: '亲密度', dataIndex: 'intimacy', key: 'intimacy', width: 100, sorter: (a: any, b: any) => a.intimacy - b.intimacy },
  { title: '操作', key: 'actions', width: 120 },
]

// 状态标签
const statusLabels: Record<string, string> = { active: '活跃', past: '过去', broken: '破裂', complicated: '复杂' }

// 重建
const showRebuild = ref(false)
async function rebuild() {
  if (!await msg.confirm('AI 将重新分析所有角色关系，可能需要 30-60 秒，期间请勿离开页面。确认开始？')) return
  showRebuild.value = true
  msg.info('AI 正在分析角色关系，请耐心等待…')
  try {
    await API.relation.autoRebuild()
    msg.success('AI 已重新分析角色关系')
    await refresh()
    await loadRelations()
  } catch (e: any) {
    msg.error('分析失败：' + formatError(e))
  } finally {
    showRebuild.value = false
  }
}
</script>

<template>
  <PageHeader title="🗺️ 角色关系图谱">
    <template #actions>
      <a-button v-if="viewMode === 'chart'" size="small" @click="autoLayout">🔄 重置布局</a-button>
      <a-button type="default" @click="openAdd">＋ 添加关系</a-button>
      <a-button type="primary" :loading="showRebuild" @click="rebuild">{{ showRebuild ? '分析中…' : '🤖 AI 重新分析' }}</a-button>
    </template>
  </PageHeader>

  <div class="page-content">
    <div class="view-tabs">
      <a-radio-group v-model:value="viewMode" button-style="solid" size="small">
        <a-radio-button value="chart">图谱视图</a-radio-button>
        <a-radio-button value="table">表格视图</a-radio-button>
        <a-radio-button value="change_log">📋 变化日志</a-radio-button>
        <a-radio-button value="manage_types">🏷️ 管理类型</a-radio-button>
      </a-radio-group>
    </div>
    <a-alert v-if="!graph?.nodes?.length" message="暂无角色，请先在「角色设定」中创建角色" type="info" show-icon />

    <template v-else>
      <!-- Vue Flow 图谱视图 -->
      <div v-if="viewMode === 'chart'" class="chart-wrap">
        <div class="flow-card">
          <ClientOnly>
            <VueFlow :nodes="vfNodes" :edges="vfEdges" :default-viewport="{ zoom: 0.8 }" fit-view-on-init>
              <Background />
              <Controls />
              <MiniMap />
            </VueFlow>
            <template #fallback>
              <div style="height:500px;display:flex;align-items:center;justify-content:center;color:#8C8C8C;">加载关系图谱…</div>
            </template>
          </ClientOnly>
        </div>
        <div class="legend">
          <span v-for="(label, key) in categoryLabel" :key="key" class="legend-item">
            <span class="dot" :style="{ background: categoryColor[key] }"></span>{{ label }}
          </span>
          <span class="legend-hint">💡 可拖拽节点调整位置，滚轮缩放</span>
        </div>
      </div>

      <!-- 表格视图 -->
      <div v-else-if="viewMode === 'table'">
        <div class="legend" style="margin-bottom: 12px">
          <span v-for="(label, key) in categoryLabel" :key="key" class="legend-item">
            <span class="dot" :style="{ background: categoryColor[key] }"></span>{{ label }}
          </span>
        </div>
        <a-table :columns="tableColumns" :data-source="tableData" :pagination="{ pageSize: 15 }" size="middle">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'relation_type'">
              <span class="rel-type" :style="{ color: categoryColor[record.category] }">{{ record.relation_type }}</span>
            </template>
            <template v-else-if="column.key === 'category_label'">
              <a-tag :color="{ family: 'pink', romantic: 'orange', hostile: 'red', professional: 'blue', social: 'cyan' }[record.category] || 'default'">
                {{ record.category_label }}
              </a-tag>
            </template>
            <template v-else-if="column.key === 'intimacy'">
              <span :class="['intimacy', { negative: record.intimacy < 0 }]">
                {{ record.intimacy > 0 ? '+' : '' }}{{ record.intimacy }}
              </span>
            </template>
            <template v-else-if="column.key === 'actions'">
              <a-button type="link" size="small" @click="openEdit(record)">编辑</a-button>
              <a-button type="link" danger size="small" @click="onDelete(record)">删除</a-button>
            </template>
          </template>
        </a-table>
      </div>

      <!-- 变化日志视图 -->
      <div v-if="viewMode === 'change_log'">
        <div style="margin-bottom:12px;display:flex;align-items:center;gap:12px;">
          <a-button size="small" :loading="loadingLogs" @click="loadAllChangeLogs">🔄 刷新日志</a-button>
          <span style="font-size:12px;color:#888;">章节生成后自动分析记录的关系变化</span>
        </div>
        <div v-if="allChangeLogs.length" class="log-timeline">
          <div v-for="log in allChangeLogs" :key="log.id" class="log-entry">
            <span class="log-chapter-badge">第{{ log.chapter_number }}章</span>
            <span class="log-pair">{{ log.char_a || '?' }} ↔ {{ log.char_b || '?' }}</span>
            <span class="log-change">{{ formatChanges(log.changed_fields) }}</span>
            <span v-if="log.summary" class="log-note">{{ log.summary }}</span>
            <a-button type="link" danger size="small" @click="onDeleteLog(log.id, log.relation_id)" style="flex-shrink:0">✕</a-button>
          </div>
        </div>
        <a-empty v-else-if="!loadingLogs" description="暂无变化记录。章节生成后自动分析会在此处记录角色关系变化。" />
      </div>

      <!-- 管理类型视图 -->
      <div v-if="viewMode === 'manage_types'" class="manage-types">
        <!-- 颜色图例 -->
        <div style="margin-bottom:12px;padding:8px 12px;background:#fafafa;border-radius:6px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
          <span style="font-size:12px;color:#888;">分类颜色：</span>
          <span v-for="(label, key) in categoryLabel" :key="key" style="display:flex;align-items:center;gap:4px;font-size:12px;">
            <span class="legend-dot" :style="{ background: categoryColor[key] }"></span>{{ label }}
          </span>
        </div>
        <div style="margin-bottom:12px;display:flex;align-items:center;gap:12px;">
          <a-button type="primary" size="small" @click="showAddType = true">＋ 添加类型</a-button>
          <span style="font-size:12px;color:#888;">编辑/删除类型，重命名会批量更新全部关系</span>
        </div>
        <div v-if="(relationTypes || []).filter((x:any) => x.name !== 'template').length" class="types-grid2">
          <a-card v-for="t in (relationTypes || []).filter((x:any) => x.name !== 'template')" :key="t.name" size="small" hoverable class="type-card2">
            <template #title>
              <div style="display:flex;align-items:center;gap:8px;">
                <span class="type-dot2" :style="{ background: categoryColor[t.category] || colorForType(t.name) }"></span>
                <template v-if="renamingType === t.name">
                  <a-input v-model:value="renameTarget" size="small" style="width:110px" @press-enter="onRenameType" />
                  <a-select v-model:value="editCategory" size="small" style="width:80px">
                    <a-select-option v-for="(label, key) in categoryLabel" :key="key" :value="key">{{ label }}</a-select-option>
                  </a-select>
                  <a-button size="small" type="primary" @click="onRenameType">确定</a-button>
                  <a-button size="small" @click="renamingType = null">取消</a-button>
                </template>
                <template v-else>
                  <span class="type-name2">{{ t.name }}</span>
                  <a-tag v-if="t.category" size="small" :color="{family:'pink',romantic:'orange',hostile:'red',professional:'blue',social:'cyan'}[t.category]||'default'">{{ {family:'亲情',romantic:'情感',hostile:'敌对',professional:'职业',social:'社交'}[t.category] || t.category }}</a-tag>
                </template>
              </div>
            </template>
            <div style="display:flex;align-items:center;justify-content:space-between;">
              <span style="color:#888;font-size:12px;">{{ t.count }} 条关系</span>
            </div>
            <template #actions>
              <a-button size="small" @click="openRenameType(t)">✏️ 编辑</a-button>
              <a-button size="small" danger @click="onDeleteTypeItem(t)">🗑 删除</a-button>
            </template>
          </a-card>
        </div>
        <a-empty v-else description="暂无关系类型" />
      </div>
    </template>
  </div>

  <!-- 添加类型弹窗 -->
  <a-modal v-model:open="showAddType" title="添加关系类型" width="400px" @ok="onAddType">
    <a-form-item label="类型名称">
      <a-input v-model:value="newTypeName" placeholder="如：难友、青梅竹马" @press-enter="onAddType" />
    </a-form-item>
    <a-form-item label="所属分类">
      <a-select v-model:value="newTypeCategory">
        <a-select-option v-for="(label, key) in categoryLabel" :key="key" :value="key">{{ label }}</a-select-option>
      </a-select>
    </a-form-item>
  </a-modal>

  <!-- 添加/编辑关系弹窗 -->
  <a-modal v-model:open="showForm" :title="editing ? '编辑关系' : '添加关系'" width="520px">
    <a-form layout="vertical">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
        <a-form-item label="角色 A">
          <a-select v-model:value="form.from_character_id" show-search placeholder="选择角色" :filter-option="(input:string, option:any) => (option.label||'').includes(input)">
            <a-select-option v-for="c in (characters || [])" :key="c.id" :value="c.id" :label="c.name">{{ c.name }}（{{ c.role }}）</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="角色 B">
          <a-select v-model:value="form.to_character_id" show-search placeholder="选择角色" :filter-option="(input:string, option:any) => (option.label||'').includes(input)">
            <a-select-option v-for="c in (characters || [])" :key="c.id" :value="c.id" :label="c.name">{{ c.name }}（{{ c.role }}）</a-select-option>
          </a-select>
        </a-form-item>
      </div>
      <a-form-item label="关系类型">
        <a-auto-complete v-model:value="form.relation_type" :options="commonRelationTypes.map(t => ({ value: t }))" placeholder="如：同伴、宿敌、难友（可自由输入）" />
      </a-form-item>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
        <a-form-item label="分类">
          <a-select v-model:value="form.category">
            <a-select-option v-for="(label, key) in categoryLabel" :key="key" :value="key">{{ label }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="亲密度">
          <a-input-number v-model:value="form.intimacy" :min="-100" :max="100" style="width:100%" />
        </a-form-item>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
        <a-form-item label="状态">
          <a-select v-model:value="form.status">
            <a-select-option value="active">活跃</a-select-option>
            <a-select-option value="past">过去</a-select-option>
            <a-select-option value="broken">破裂</a-select-option>
            <a-select-option value="complicated">复杂</a-select-option>
          </a-select>
        </a-form-item>
        <span></span>
      </div>
      <a-form-item label="描述">
        <a-textarea v-model:value="form.description" :rows="2" placeholder="可选：关系的简短描述" />
      </a-form-item>
    </a-form>
    <template #footer>
      <a-button @click="showForm = false">取消</a-button>
      <a-button type="primary" @click="onSave">保存</a-button>
    </template>
  </a-modal>
</template>

<style scoped>
.chart-wrap { display: flex; flex-direction: column; gap: 12px; }
.view-tabs { margin-bottom: 14px; display:flex; align-items:center; }
/* 变化日志时间线 */
.log-timeline { max-height: 500px; overflow-y: auto; }
.log-entry { display:flex; align-items:center; gap:12px; padding:8px 0; border-bottom:1px solid #f5f5f5; font-size:13px; }
.log-entry:last-child { border-bottom:none; }
.log-chapter-badge { background:#EAF0F1; color:#4D8088; font-weight:600; padding:2px 8px; border-radius:4px; font-size:12px; white-space:nowrap; }
.log-pair { font-weight:500; white-space:nowrap; }
.log-change { color:#333; font-size:12px; }
.log-note { color:#888; font-size:11px; flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
/* 管理类型 */
.types-grid2 { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:14px; }
.type-card2 { border-radius:10px; }
.type-dot2 { width:12px; height:12px; border-radius:50%; flex-shrink:0; }
.type-name2 { font-size:15px; font-weight:600; }
.manage-types { }
.legend-dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
.flow-card { background: #fafafa; border: 1px solid #e8e8e8; border-radius: 8px; height: 540px; overflow: hidden; }
/* Vue Flow 根元素需撑满容器高度才可见 */
.flow-card :deep(.vue-flow) { width: 100%; height: 100%; }
.legend { display: flex; gap: 14px; font-size: 12px; flex-wrap: wrap; align-items: center; }
.legend-item { display: flex; align-items: center; gap: 4px; }
.legend-hint { color: #B5C7CB; font-size: 11px; margin-left: auto; }
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.rel-type { font-weight: 600; }
.intimacy { color: #6B9CA4; font-weight: 600; }
.intimacy.negative { color: #f44336; }
.rel-types-section { margin-top: 16px; padding: 10px 12px; background: #fafafa; border: 1px solid #f0f0f0; border-radius: 8px; }
.rel-types-label { font-size: 12px; color: #888; margin-right: 8px; }
</style>
