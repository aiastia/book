<script setup lang="ts">
// MCP 服务器管理
import { API } from '~/composables/api'
import { apiGet, apiPost, apiPut, apiDelete } from '~/composables/useApi'

useHead({ title: 'MCP 管理 — 墨语' })
const msg = useMessage()

const servers = ref<any[]>([])
const loading = ref(false)
const showForm = ref(false)
const editing = ref<any>(null)
const form = reactive({ name: '', url: '', description: '', transport: 'streamable-http', api_key: '' })
const saving = ref(false)

async function refresh() {
  loading.value = true
  try { servers.value = await apiGet<any[]>('/api/mcp/servers') || [] }
  catch { servers.value = [] }
  finally { loading.value = false }
}

function openCreate() {
  form.name = ''; form.url = ''; form.description = ''; form.transport = 'streamable-http'; form.api_key = ''
  editing.value = null; showForm.value = true
}

function openEdit(s: any) {
  form.name = s.name; form.url = s.url; form.description = s.description || ''
  form.transport = s.transport || 'streamable-http'; form.api_key = (s.config || {}).api_key || ''
  editing.value = s; showForm.value = true
}

async function onSave() {
  if (!form.name.trim() || !form.url.trim()) { msg.warning('名称和 URL 必填'); return }
  saving.value = true
  try {
    if (editing.value) {
      await apiPut(`/api/mcp/servers/${editing.value.id}`, { ...editing.value, ...form })
    } else {
      await apiPost('/api/mcp/servers', { ...form })
    }
    showForm.value = false; await refresh(); msg.success('保存成功')
  } catch (e: any) { msg.error('保存失败：' + formatError(e)) }
  finally { saving.value = false }
}

async function onDelete(s: any) {
  if (!await msg.confirm(`确认删除 MCP Server「${s.name}」？`)) return
  try { await apiDelete(`/api/mcp/servers/${s.id}`); await refresh(); msg.success('已删除') }
  catch (e: any) { msg.error('删除失败：' + formatError(e)) }
}

async function onToggle(s: any) {
  try {
    await apiPut(`/api/mcp/servers/${s.id}`, { enabled: !s.enabled })
    await refresh()
  } catch (e: any) { msg.error('操作失败') }
}

const discovering = ref<number | null>(null)
async function onDiscover(s: any) {
  discovering.value = s.id
  try {
    const res = await apiPost<any>(`/api/mcp/servers/${s.id}/discover`, {})
    msg.success(`发现 ${res.count || 0} 个工具`)
  } catch (e: any) { msg.error('发现失败：' + formatError(e)) }
  finally { discovering.value = null }
}

await refresh()
</script>

<template>
  <div style="max-width:800px;margin:0 auto">
    <PageHeader title="MCP 服务器管理" back="/books">
      <template #actions>
        <a-button type="primary" @click="openCreate">+ 添加服务器</a-button>
      </template>
    </PageHeader>

    <a-alert type="info" show-icon style="margin-bottom:16px"
      message="MCP 服务器提供额外的 AI 工具（搜索、数据库查询等）。启用后，AI 写作时可自动调用这些工具获取信息。" />

    <a-spin :spinning="loading">
      <div v-if="servers.length" style="display:flex;flex-direction:column;gap:12px">
        <a-card v-for="s in servers" :key="s.id" size="small">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
              <span style="font-weight:600;font-size:15px">{{ s.name }}</span>
              <a-tag :color="s.enabled ? 'green' : 'default'" size="small" style="margin-left:8px">
                {{ s.enabled ? '已启用' : '已禁用' }}
              </a-tag>
            </div>
            <a-switch :checked="s.enabled" size="small" @change="onToggle(s)" />
          </div>
          <div style="font-size:12px;color:#8C8C8C;margin-top:4px">{{ s.url }}</div>
          <div v-if="s.description" style="font-size:12px;color:#595959;margin-top:4px">{{ s.description }}</div>
          <div style="margin-top:8px;display:flex;gap:8px">
            <a-button size="small" @click="openEdit(s)">编辑</a-button>
            <a-button size="small" :loading="discovering === s.id" @click="onDiscover(s)">发现工具</a-button>
            <a-button size="small" danger @click="onDelete(s)">删除</a-button>
          </div>
        </a-card>
      </div>
      <a-empty v-else description="暂无 MCP 服务器，点击右上角添加" />
    </a-spin>

    <!-- 表单弹窗 -->
    <a-modal v-model:open="showForm" :title="editing ? '编辑 MCP 服务器' : '添加 MCP 服务器'" width="500px" @ok="onSave" :confirm-loading="saving">
      <a-form layout="vertical">
        <a-form-item label="名称" required><a-input v-model:value="form.name" placeholder="如：搜索工具" /></a-form-item>
        <a-form-item label="URL" required><a-input v-model:value="form.url" placeholder="如：http://localhost:8080" /></a-form-item>
        <a-form-item label="传输协议">
          <a-select v-model:value="form.transport">
            <a-select-option value="streamable-http">streamable-http（推荐）</a-select-option>
            <a-select-option value="stdio">stdio</a-select-option>
            <a-select-option value="sse">sse</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="描述"><a-textarea v-model:value="form.description" :rows="2" placeholder="简要描述此服务器提供的功能" /></a-form-item>
        <a-form-item label="API Key（如需要）"><a-input v-model:value="form.api_key" placeholder="Tavily Search 的 API Key" /></a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>
