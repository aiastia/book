<script setup lang="ts">
// 用户管理（#4）+ 系统统计
import { apiGet, apiPost, apiPut, apiDelete } from '~/composables/useApi'
import { useAuth } from '~/composables/useAuth'
useHead({ title: '用户管理 — 墨语' })
const msg = useMessage()
const { user } = useAuth()

const loading = ref(false)
const users = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const stats = ref<any>({})

async function loadUsers() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.set('page', String(page.value))
    params.set('page_size', String(pageSize.value))
    if (keyword.value) params.set('keyword', keyword.value)
    const r = await apiGet<any>(`/api/admin/users?${params.toString()}`)
    users.value = r.items || []
    total.value = r.total || 0
  } catch (e: any) {
    msg.error('加载失败：' + formatError(e))
  } finally {
    loading.value = false
  }
}
async function loadStats() {
  try { stats.value = await apiGet<any>('/api/admin/stats') } catch {}
}
onMounted(() => { loadUsers(); loadStats() })

function onSearch() { page.value = 1; loadUsers() }

// 创建用户
const showAdd = ref(false)
const newUser = reactive({ username: '', password: '', email: '', nickname: '', is_admin: false })
const createdPwd = ref('')
async function onAdd() {
  if (!newUser.username.trim()) return
  try {
    const r = await apiPost<any>('/api/admin/users', { ...newUser })
    showAdd.value = false
    createdPwd.value = r.initial_password || ''
    newUser.username = ''; newUser.password = ''; newUser.email = ''
    await loadUsers(); await loadStats()
    msg.success('用户已创建')
  } catch (e: any) { msg.error('创建失败：' + formatError(e)) }
}

// 重置密码
const resetResult = ref<{ user: string; pwd: string } | null>(null)
async function onReset(u: any) {
  if (!await msg.confirm(`确认重置「${u.username}」的密码？`)) return
  try {
    const r = await apiPost<{ new_password: string }>(`/api/admin/users/${u.id}/reset-password`, {})
    resetResult.value = { user: u.username, pwd: r.new_password }
    msg.success('密码已重置')
  } catch (e: any) { msg.error('重置失败：' + formatError(e)) }
}

// 切换管理员/启用状态
async function onToggle(u: any, field: 'is_admin' | 'is_active') {
  const val = !u[field]
  const label = field === 'is_admin' ? '管理员' : '启用'
  if (field === 'is_admin' && val && !await msg.confirm(`确认授予「${u.username}」管理员权限？`)) return
  try {
    await apiPut(`/api/admin/users/${u.id}`, { [field]: val })
    await loadUsers()
    msg.success(`${label}状态已更新`)
  } catch (e: any) { msg.error('更新失败：' + formatError(e)) }
}

async function onDelete(u: any) {
  if (!await msg.confirm(`确认删除用户「${u.username}」？此操作不可恢复！`)) return
  try {
    await apiDelete(`/api/admin/users/${u.id}`)
    await loadUsers(); await loadStats()
    msg.success('已删除')
  } catch (e: any) { msg.error('删除失败：' + formatError(e)) }
}

const columns = [
  { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
  { title: '用户名', dataIndex: 'username', key: 'username' },
  { title: '昵称', dataIndex: 'nickname', key: 'nickname' },
  { title: '邮箱', dataIndex: 'email', key: 'email' },
  { title: '管理员', key: 'is_admin', width: 90 },
  { title: '状态', key: 'is_active', width: 90 },
  { title: '注册时间', dataIndex: 'created_at', key: 'created_at', width: 160 },
  { title: '操作', key: 'actions', width: 240, fixed: 'right' as const },
]
</script>

<template>
	  <PageHeader title="用户管理" back="/books">
    <template #actions>
      <a-button @click="loadUsers">刷新</a-button>
      <a-button type="primary" @click="showAdd = true">+ 创建用户</a-button>
    </template>
  </PageHeader>

  <div class="page-content">
    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card"><div class="stat-label">总用户</div><div class="stat-value">{{ stats.users || 0 }}</div></div>
      <div class="stat-card admin"><div class="stat-label">管理员</div><div class="stat-value">{{ stats.admins || 0 }}</div></div>
      <div class="stat-card active"><div class="stat-label">活跃用户</div><div class="stat-value">{{ stats.active_users || 0 }}</div></div>
      <div class="stat-card"><div class="stat-label">总项目</div><div class="stat-value">{{ stats.projects || 0 }}</div></div>
      <div class="stat-card"><div class="stat-label">总章节</div><div class="stat-value">{{ stats.chapters || 0 }}</div></div>
    </div>

    <!-- 搜索 -->
    <div class="search-bar">
      <a-input-search v-model:value="keyword" placeholder="搜索用户名/邮箱/昵称" enter-button @search="onSearch" style="width: 320px" allow-clear />
    </div>

    <!-- 用户表 -->
    <a-table :columns="columns" :data-source="users" :loading="loading" row-key="id" size="middle" :pagination="false">
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'is_admin'">
          <a-switch :checked="record.is_admin" size="small" @change="onToggle(record, 'is_admin')" />
        </template>
        <template v-else-if="column.key === 'is_active'">
          <a-tag :color="record.is_active ? 'success' : 'default'">{{ record.is_active ? '启用' : '禁用' }}</a-tag>
          <a-switch :checked="record.is_active" size="small" style="margin-left:6px" @change="onToggle(record, 'is_active')" />
        </template>
        <template v-else-if="column.key === 'actions'">
          <a-button type="link" size="small" @click="onReset(record)">重置密码</a-button>
          <a-button type="link" danger size="small" :disabled="record.id === user?.id" @click="onDelete(record)">删除</a-button>
        </template>
        <template v-else-if="column.key === 'created_at'">
          {{ record.created_at?.substring(0, 16).replace('T', ' ') }}
        </template>
      </template>
    </a-table>

    <!-- 创建用户 -->
    <a-modal v-model:open="showAdd" title="创建用户" width="480px">
      <a-form layout="vertical">
        <a-form-item label="用户名 *"><a-input v-model:value="newUser.username" /></a-form-item>
        <a-form-item label="密码（留空自动生成）"><a-input-password v-model:value="newUser.password" placeholder="留空则自动生成" /></a-form-item>
        <a-form-item label="邮箱"><a-input v-model:value="newUser.email" /></a-form-item>
        <a-form-item label="昵称"><a-input v-model:value="newUser.nickname" /></a-form-item>
        <a-form-item><a-checkbox v-model:checked="newUser.is_admin">设为管理员</a-checkbox></a-form-item>
      </a-form>
      <template #footer>
        <a-button @click="showAdd = false">取消</a-button>
        <a-button type="primary" @click="onAdd">创建</a-button>
      </template>
    </a-modal>

    <!-- 密码结果 -->
    <a-modal :open="!!resetResult || !!createdPwd" @cancel="() => { resetResult = null; createdPwd = '' }" title="密码已重置" width="460px" :footer="null">
      <a-alert
        :message="resetResult ? `用户「${resetResult.user}」的新密码` : '新建用户初始密码'"
        :description="resetResult?.pwd || createdPwd"
        type="success" show-icon
      />
      <div style="margin-top:12px;text-align:center;">
        <a-button type="primary" @click="() => { resetResult = null; createdPwd = '' }">我已记录</a-button>
      </div>
    </a-modal>
  </div>
</template>

<style scoped>
.stats-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-bottom: 16px; }
.stat-card { background: #fff; border: 1px solid #e8e8e8; border-radius: 8px; padding: 12px 14px; position: relative; overflow: hidden; }
.stat-card::before { content:''; position:absolute; top:0; left:0; width:3px; height:100%; background:#8C8C8C; }
.stat-card.admin::before { background: #C75B5B; }
.stat-card.active::before { background: #52A569; }
.stat-label { font-size: 11px; color: #8C8C8C; margin-bottom: 4px; }
.stat-value { font-size: 22px; font-weight: 600; }
.search-bar { margin-bottom: 16px; }
</style>
