<script setup lang="ts">
// 组织与势力：左右分栏（对标 MuMu Organizations.tsx）
// 左侧组织列表（树形）+ 右侧选中组织详情 + 内嵌成员表格
import { API } from '~/composables/api'
import { useProject } from '~/composables/useProject'
import { useBackgroundTasks } from '~/composables/useBackgroundTasks'
import { apiGet } from '~/composables/useApi'
import type { Character } from '~/composables/api/types'
useHead({ title: '组织与势力 — 墨语' })
const { currentProjectId } = useProject()
if (!currentProjectId.value) await navigateTo('/books')
const msg = useMessage()
const { onTaskCompleted } = useBackgroundTasks()
const { data: tree, refresh: refreshTree } = await useFetch<any[]>(() => `/projects/${currentProjectId.value}/organizations/tree`)
const { data: characters, refresh: refreshChars } = await useFetch<Character[]>(() => `/projects/${currentProjectId.value}/characters`)

// 当组织生成/初始化任务完成时自动刷新列表
onTaskCompleted('organizations', () => { refresh() })
onTaskCompleted('init', () => { setTimeout(() => refreshTree(), 2000) })

const generating = ref(false)
const showGen = ref(false)
const showAdd = ref(false)
const newOrg = reactive({ name: '', org_type: '', description: '' })
const editing = ref<any>(null)
const editForm = reactive({ name: '', org_type: '', description: '', power_value: 50, location: '', motto: '', color: '' })
const genCount = ref(3)
const genReq = ref('')

// 选中组织
const selectedOrgId = ref<number | null>(null)
const selectedOrg = ref<any>(null)
const members = ref<any[]>([])
const loadingMembers = ref(false)

// 展开/折叠
const expanded = ref<Set<number>>(new Set())
function toggle(id: number) {
  if (expanded.value.has(id)) expanded.value.delete(id)
  else expanded.value.add(id)
}
function flattenTree(nodes: any[], level = 0): any[] {
  const out: any[] = []
  for (const n of nodes) {
    out.push({ ...n, _level: level })
    if (n.children?.length && expanded.value.has(n.id)) {
      out.push(...flattenTree(n.children, level + 1))
    }
  }
  return out
}
const flatList = computed(() => flattenTree(tree.value || []))

// 选中组织后加载成员
async function selectOrg(o: any) {
  selectedOrgId.value = o.id
  selectedOrg.value = o
  await loadMembers(o.id)
}
async function loadMembers(orgId: number) {
  loadingMembers.value = true
  try {
    members.value = await apiGet<any[]>(`/api/projects/${currentProjectId.value}/organizations/${orgId}/members`)
  } catch (e: any) { msg.error('加载成员失败：' + formatError(e)) }
  finally { loadingMembers.value = false }
}

// 成员管理
const showAddMember = ref(false)
const showEditMember = ref(false)
const editMemberId = ref<number | null>(null)
const newMember = reactive({ character_id: null as number | null, position: '', rank: 5, loyalty: 60, contribution: 30, status: 'active', joined_at: '', notes: '' })
const genMembersLoading = ref(false)
async function onAddMember() {
  if (!newMember.character_id || !selectedOrgId.value) return
  try {
    await API.organization.addMember(selectedOrgId.value, { ...newMember })
    showAddMember.value = false
    newMember.character_id = null; newMember.position = ''
    await loadMembers(selectedOrgId.value)
    await refreshTree()
    msg.success('已添加')
  } catch (e: any) { msg.error('添加失败：' + formatError(e)) }
}
function openEditMember(m: any) {
  editMemberId.value = m.id
  Object.assign(newMember, { character_id: m.character_id, position: m.position || '', rank: m.rank || 5, loyalty: m.loyalty || 50, contribution: m.contribution || 30, status: m.status || 'active', joined_at: m.joined_at || '', notes: m.notes || '' })
  showEditMember.value = true
}
async function onSaveMember() {
  if (!selectedOrgId.value || !editMemberId.value) return
  try {
    await API.organization.updateMember(selectedOrgId.value, editMemberId.value, { ...newMember })
    showEditMember.value = false; editMemberId.value = null
    await loadMembers(selectedOrgId.value); await refreshTree()
    msg.success('已更新')
  } catch (e: any) { msg.error('更新失败：' + formatError(e)) }
}
async function onRemoveMember(memberId: number) {
  if (!selectedOrgId.value) return
  try { await API.organization.removeMember(selectedOrgId.value, memberId); await loadMembers(selectedOrgId.value); await refreshTree(); msg.success('已移除') }
  catch (e: any) { msg.error('移除失败：' + formatError(e)) }
}
async function onGenMembers() {
  if (!selectedOrgId.value) return
  if (!await msg.confirm('AI 将根据角色性格和组织特征，为该组织自动分配成员。确认开始？')) return
  genMembersLoading.value = true
  try {
    const r = await API.organization.generateMembers(selectedOrgId.value, { user_prompt: '' })
    await loadMembers(selectedOrgId.value); await refreshTree()
    msg.success(`AI 分配了 ${r.count} 名成员`)
  } catch (e: any) { msg.error('生成失败：' + formatError(e)) }
  finally { genMembersLoading.value = false }
}

async function onGenerate() {
  generating.value = true
  try {
    const { task_id } = await API.organization.generateAsync({ count: genCount.value, user_input: genReq.value })
    const { trackTask } = useBackgroundTasks()
    trackTask({ id: task_id, task_type: 'organizations', title: `生成 ${genCount.value} 个组织` })
    showGen.value = false
    msg.success('生成任务已提交，可在右下角查看进度')
  } catch (e: any) { msg.error('生成失败：' + formatError(e)) }
  finally { generating.value = false }
}
async function onAdd() {
  if (!newOrg.name.trim()) return
  try { await API.organization.create({ ...newOrg }); showAdd.value = false; newOrg.name = ''; await refreshTree() }
  catch (e: any) { msg.error('添加失败：' + formatError(e)) }
}
function openEdit(o: any) {
  editing.value = o
  Object.assign(editForm, { name: o.name, org_type: o.org_type || '', description: o.description || '', power_value: o.power_value || 50, location: o.location || '', motto: o.motto || '', color: o.color || '' })
}
async function onSave() {
  if (!selectedOrgId.value) return
  try { await API.organization.update(selectedOrgId.value, { ...editForm }); await refreshTree(); editing.value = null; msg.success('已保存') }
  catch (e: any) { msg.error('保存失败：' + formatError(e)) }
}
async function onDelete(id: number) {
  if (!await msg.confirm('确认删除？')) return
  try { await API.organization.delete(id); selectedOrgId.value = null; selectedOrg.value = null; await refreshTree(); msg.success('已删除') }
  catch (e: any) { msg.error('删除失败：' + formatError(e)) }
}

const memberColumns = [
  { title: '姓名', dataIndex: 'character_name', key: 'name', width: 100 },
  { title: '职位', dataIndex: 'position', key: 'position', width: 130 },
  { title: '忠诚度', dataIndex: 'loyalty', key: 'loyalty', width: 80 },
  { title: '贡献度', dataIndex: 'contribution', key: 'contribution', width: 80 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 70 },
  { title: '加入时间', dataIndex: 'joined_at', key: 'joined', width: 90 },
  { title: '操作', key: 'actions', width: 100 },
]
function loyaltyColor(v: number) { return v >= 70 ? '#52A569' : v >= 40 ? '#D49A4E' : '#C75B5B' }
const initAllLoading = ref(false)
async function onInitAllMembers() {
  if (!await msg.confirm('AI 将为所有尚无成员的组织自动分配成员（已有成员的跳过）。确认开始？')) return
  initAllLoading.value = true
  try {
    const r = await API.organization.generateAllMembers()
    await refreshTree()
    msg.success(`完成：${r.created} 个新成员分配至 ${r.results.filter((x:any) => !x.skipped && !x.error).length} 个组织`)
  } catch (e: any) { msg.error('失败：' + formatError(e)) }
  finally { initAllLoading.value = false }
}
</script>

<template>
  <PageHeader title="组织与势力">
    <template #actions>
      <a-button type="primary" :loading="generating" @click="showGen = true">AI 生成组织</a-button>
      <a-button :loading="initAllLoading" @click="onInitAllMembers">🤖 一键分配全员</a-button>
      <a-button @click="showAdd = true">+ 添加</a-button>
    </template>
  </PageHeader>

  <div class="page-content">
    <div class="org-layout">
      <!-- 左侧组织列表 -->
      <div class="org-list-panel">
        <div class="panel-title">组织列表</div>
        <a-empty v-if="!flatList.length" description="暂无组织" />
        <div v-for="o in flatList" :key="o.id" class="org-item" :class="{ active: selectedOrgId === o.id }"
          :style="{ marginLeft: (o._level * 20) + 'px' }" @click="selectOrg(o)">
          <span v-if="o.children?.length" class="toggle" @click.stop="toggle(o.id)">{{ expanded.has(o.id) ? '▼' : '▶' }}</span>
          <span v-else class="toggle ph"></span>
          <span class="org-icon">🏛️</span>
          <span class="org-name">{{ o.name }}</span>
          <span v-if="o.member_count" class="mem-cnt">{{ o.member_count }}</span>
        </div>
      </div>

      <!-- 右侧详情 + 成员表格 -->
      <div class="org-detail-panel">
        <a-empty v-if="!selectedOrg" description="← 请从左侧选择一个组织" />
        <template v-else>
          <!-- 组织详情 -->
          <a-card size="small" style="margin-bottom:12px;">
            <div class="detail-head">
              <div>
                <h3 class="detail-name">{{ selectedOrg.name }}</h3>
                <div class="detail-tags">
                  <a-tag v-if="selectedOrg.org_type" color="blue">{{ selectedOrg.org_type }}</a-tag>
                  <span class="detail-power">
                    <span class="power-label">势力</span>
                    <span class="power-track"><span class="power-fill" :style="{ width: selectedOrg.power_value + '%' }"></span></span>
                    <span class="power-num">{{ selectedOrg.power_value }}</span>
                  </span>
                </div>
              </div>
              <div class="detail-actions">
                <a-button size="small" @click="openEdit(selectedOrg)">编辑</a-button>
                <a-button size="small" danger @click="onDelete(selectedOrg.id)">删除</a-button>
              </div>
            </div>
            <a-descriptions :column="2" size="small" style="margin-top:10px;">
              <a-descriptions-item label="所在地">{{ selectedOrg.location || '—' }}</a-descriptions-item>
              <a-descriptions-item label="成员数">{{ selectedOrg.member_count || 0 }} 人</a-descriptions-item>
              <a-descriptions-item label="代表颜色" :span="2">{{ selectedOrg.color || '—' }}</a-descriptions-item>
              <a-descriptions-item label="格言/口号" :span="2">{{ selectedOrg.motto || '—' }}</a-descriptions-item>
              <a-descriptions-item label="组织目的/简介" :span="2">{{ selectedOrg.description || '—' }}</a-descriptions-item>
            </a-descriptions>
          </a-card>
          <!-- 成员表格 -->
          <a-card size="small" title="成员列表" :body-style="{ padding: '12px' }">
            <template #extra>
              <a-button size="small" type="primary" @click="showAddMember = true">+ 添加成员</a-button>
              <a-button size="small" :loading="genMembersLoading" @click="onGenMembers" style="margin-left:6px">🤖 AI 分配</a-button>
            </template>
            <a-table :columns="memberColumns" :data-source="members" :loading="loadingMembers" row-key="id" size="small" :pagination="false">
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'loyalty'">
                  <a-progress :percent="record.loyalty" :size="20" :show-info="false" stroke-color="#52A569" trail-color="#F0F0F0" />
                  <span :style="{ color: loyaltyColor(record.loyalty), fontWeight: 600, fontSize:'12px' }">{{ record.loyalty }}%</span>
                </template>
                <template v-else-if="column.key === 'contribution'">
                  <span :style="{ color: loyaltyColor(record.contribution), fontWeight: 600 }">{{ record.contribution }}%</span>
                </template>
                <template v-else-if="column.key === 'status'">
                  <a-tag :color="record.status === 'active' ? 'green' : record.status === 'deceased' ? 'red' : record.status === 'expelled' ? 'orange' : 'default'" size="small">{{ { active: '在职', retired: '退隐', expelled: '驱逐', deceased: '已故' }[record.status] || record.status }}</a-tag>
                </template>
                <template v-else-if="column.key === 'actions'">
                  <a-button type="link" size="small" @click="openEditMember(record)">编辑</a-button>
                  <a-button type="link" danger size="small" @click="onRemoveMember(record.id)">移除</a-button>
                </template>
              </template>
            </a-table>
          </a-card>
        </template>
      </div>
    </div>

    <!-- 弹窗 -->
    <a-modal v-model:open="showGen" title="AI 生成组织" width="460px">
      <a-form layout="vertical">
        <a-form-item label="数量"><a-input-number v-model:value="genCount" :min="1" :max="8" /></a-form-item>
        <a-form-item label="需求"><a-textarea v-model:value="genReq" :rows="2" /></a-form-item>
      </a-form>
      <template #footer><a-button @click="showGen = false">取消</a-button><a-button type="primary" :loading="generating" @click="onGenerate">生成</a-button></template>
    </a-modal>
    <a-modal v-model:open="showAdd" title="添加组织" width="440px">
      <a-form layout="vertical">
        <a-form-item label="名称"><a-input v-model:value="newOrg.name" /></a-form-item>
        <a-form-item label="类型"><a-input v-model:value="newOrg.org_type" /></a-form-item>
        <a-form-item label="描述"><a-textarea v-model:value="newOrg.description" :rows="3" /></a-form-item>
      </a-form>
      <template #footer><a-button @click="showAdd = false">取消</a-button><a-button type="primary" @click="onAdd">添加</a-button></template>
    </a-modal>
    <a-modal :open="!!editing" @update:open="(v:any) => { if(!v) editing = null }" title="编辑组织" width="520px" v-if="editing">
      <a-form layout="vertical">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
          <a-form-item label="名称"><a-input v-model:value="editForm.name" /></a-form-item>
          <a-form-item label="类型"><a-input v-model:value="editForm.org_type" /></a-form-item>
        </div>
        <a-form-item label="格言/口号"><a-input v-model:value="editForm.motto" placeholder="如：以血铸剑，以剑问道" /></a-form-item>
        <a-form-item label="代表颜色">
          <a-textarea v-model:value="editForm.color" :rows="1" placeholder="如：靛青色，象征庙宇的庄重、夜色的监控与水的平衡" />
        </a-form-item>
        <a-form-item label="组织目的/简介"><a-textarea v-model:value="editForm.description" :rows="3" /></a-form-item>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
          <a-form-item label="势力值(0-100)"><a-input-number v-model:value="editForm.power_value" :min="0" :max="100" style="width:100%" /></a-form-item>
          <a-form-item label="所在地"><a-input v-model:value="editForm.location" /></a-form-item>
        </div>
      </a-form>
      <template #footer><a-button @click="editing = null">取消</a-button><a-button type="primary" @click="onSave">保存</a-button></template>
    </a-modal>
    <a-modal v-model:open="showAddMember" title="添加成员" width="440px" @ok="onAddMember">
      <a-form layout="vertical">
        <a-form-item label="选择角色">
          <a-select v-model:value="newMember.character_id" show-search>
            <a-select-option v-for="c in (characters || [])" :key="c.id" :value="c.id">{{ c.name }}（{{ c.role }}）</a-select-option>
          </a-select>
        </a-form-item>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
          <a-form-item label="职位"><a-input v-model:value="newMember.position" placeholder="如：阁主/长老" /></a-form-item>
          <a-form-item label="等级(1-10)"><a-input-number v-model:value="newMember.rank" :min="1" :max="10" style="width:100%" /></a-form-item>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
          <a-form-item label="忠诚(0-100)"><a-input-number v-model:value="newMember.loyalty" :min="0" :max="100" style="width:100%" /></a-form-item>
          <a-form-item label="贡献(0-100)"><a-input-number v-model:value="newMember.contribution" :min="0" :max="100" style="width:100%" /></a-form-item>
        </div>
        <a-form-item label="加入时间"><a-input v-model:value="newMember.joined_at" placeholder="如：第3章 / 十年前" /></a-form-item>
      </a-form>
    </a-modal>
    <!-- 编辑成员 -->
    <a-modal v-model:open="showEditMember" title="编辑成员" width="440px" @ok="onSaveMember">
      <a-form layout="vertical">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
          <a-form-item label="职位"><a-input v-model:value="newMember.position" placeholder="如：阁主/长老" /></a-form-item>
          <a-form-item label="等级(1-10)"><a-input-number v-model:value="newMember.rank" :min="1" :max="10" style="width:100%" /></a-form-item>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
          <a-form-item label="忠诚(0-100)"><a-input-number v-model:value="newMember.loyalty" :min="0" :max="100" style="width:100%" /></a-form-item>
          <a-form-item label="贡献(0-100)"><a-input-number v-model:value="newMember.contribution" :min="0" :max="100" style="width:100%" /></a-form-item>
        </div>
        <a-form-item label="状态">
          <a-select v-model:value="newMember.status">
            <a-select-option value="active">在职</a-select-option>
            <a-select-option value="retired">退隐</a-select-option>
            <a-select-option value="expelled">驱逐</a-select-option>
            <a-select-option value="deceased">已故</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="加入时间"><a-input v-model:value="newMember.joined_at" placeholder="如：第3章 / 十年前" /></a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.org-layout { display: grid; grid-template-columns: 280px 1fr; gap: 14px; }
.org-list-panel { background: #fff; border: 1px solid #E8E4DC; border-radius: 8px; padding: 10px; max-height: calc(100vh - 160px); overflow-y: auto; }
.panel-title { font-size: 13px; font-weight: 600; color: #4D8088; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid #F0EDE6; }
.org-item { display: flex; align-items: center; gap: 6px; padding: 8px 10px; border-radius: 6px; cursor: pointer; margin-bottom: 3px; transition: background .15s; }
.org-item:hover { background: #F8F6F1; }
.org-item.active { background: #EAF0F1; font-weight: 600; }
.toggle { width: 16px; font-size: 11px; color: #8C8C8C; cursor: pointer; text-align: center; }
.toggle.ph { cursor: default; }
.org-icon { font-size: 14px; }
.org-name { font-size: 13px; flex: 1; }
.mem-cnt { font-size: 11px; color: #4D8088; background: #EAF0F1; padding: 1px 6px; border-radius: 10px; }
.org-detail-panel { min-height: 400px; }
.detail-head { display: flex; justify-content: space-between; align-items: flex-start; }
.detail-name { font-size: 17px; font-weight: 600; margin: 0 0 6px 0; }
.detail-tags { display: flex; align-items: center; gap: 8px; }
.detail-power { display: flex; align-items: center; gap: 4px; font-size: 11px; }
.power-label { color: #8C8C8C; }
.power-track { width: 50px; height: 4px; background: #F0EDE6; border-radius: 999; overflow: hidden; }
.power-fill { height: 100%; background: #4D8088; border-radius: 999; }
.power-num { color: #4D8088; font-weight: 600; }
.detail-actions { display: flex; gap: 4px; }
</style>
