<script setup lang="ts">
// 故事记忆：列表 + 类型筛选 + 向量语义搜索 + 统计
// 对标 MuMuAINovel memories 页面。记忆由剧情分析自动提取，本页提供管理与语义检索。
import { API } from '~/composables/api'
import { useProject } from '~/composables/useProject'
useHead({ title: '故事记忆 — 墨语' })
const { currentProjectId } = useProject()
if (!currentProjectId.value) await navigateTo('/books')
const msg = useMessage()
const { data: memories, refresh: refresh } = await useFetch(() => `/projects/${currentProjectId.value}/memories?limit=100`)
const { data: stats } = await api.getMemoryStats()

// 类型筛选
const filterType = ref('')
const filteredMemories = computed(() => {
  const list = memories.value || []
  if (!filterType.value) return list
  return list.filter((m: any) => m.memory_type === filterType.value)
})

// 类型映射
const typeMeta: Record<string, { label: string; color: string }> = {
  summary: { label: '章节摘要', color: 'blue' },
  plot: { label: '关键情节', color: 'green' },
  character: { label: '角色变化', color: 'orange' },
  foreshadow: { label: '伏笔', color: 'purple' },
  hook: { label: '悬念钩子', color: 'red' },
  conflict: { label: '冲突', color: 'volcano' },
  world: { label: '世界观', color: 'cyan' },
  relationship: { label: '关系', color: 'magenta' },
  manual: { label: '手动', color: 'default' },
}
const importanceColor = (imp: number) => {
  if (imp >= 0.75) return '#52A569'
  if (imp >= 0.5) return '#4D8088'
  if (imp >= 0.3) return '#D49A4E'
  return '#8C8C8C'
}

// 语义搜索
const searchQuery = ref('')
const searchResults = ref<any[] | null>(null)
const searching = ref(false)
async function onSearch() {
  if (!searchQuery.value.trim()) {
    searchResults.value = null
    return
  }
  searching.value = true
  try {
    const res = await api.searchMemories({
      query: searchQuery.value,
      limit: 15,
      memory_types: filterType.value ? [filterType.value] : undefined,
    })
    searchResults.value = res || []
    if (!res?.length) msg.info('未找到相关记忆')
  } catch (e: any) {
    msg.error('语义搜索失败：' + formatError(e))
  } finally {
    searching.value = false
  }
}
function clearSearch() {
  searchQuery.value = ''
  searchResults.value = null
}

// 重建向量索引
const reindexing = ref(false)
async function onReindex() {
  if (!await msg.confirm('将为所有未向量化的记忆生成向量（可能耗时较长），确认开始？')) return
  reindexing.value = true
  try {
    const r = await api.reindexMemories()
    msg.success(`完成：已索引 ${r.indexed}/${r.total} 条记忆`)
    await refresh()
  } catch (e: any) {
    msg.error('重建失败：' + formatError(e))
  } finally {
    reindexing.value = false
  }
}

// 删除/清空
async function onDelete(id: number) {
  if (!await msg.confirm('确认删除这条记忆？')) return
  try { await API.memory.delete(id); await refresh(); msg.success('已删除') }
  catch (e: any) { msg.error('删除失败：' + formatError(e)) }
}
async function onClearAll() {
  if (!await msg.confirm('确认清空所有记忆？此操作不可恢复！')) return
  try { await API.memory.clear(); await refresh(); msg.success('已清空') }
  catch (e: any) { msg.error('清空失败：' + formatError(e)) }
}

// 手动添加
const showAdd = ref(false)
const newMemory = reactive({ memory_type: 'manual', title: '', content: '', importance: 0.6, chapter_number: null as number | null })
async function onAdd() {
  if (!newMemory.content.trim()) return
  try {
    await API.memory.create({ ...newMemory })
    showAdd.value = false
    newMemory.content = ''; newMemory.title = ''
    await refresh()
    msg.success('已添加')
  } catch (e: any) {
    msg.error('添加失败：' + formatError(e))
  }
}

const displayList = computed(() => searchResults.value ?? filteredMemories.value)
</script>

<template>
  <PageHeader title="故事记忆">
    <template #actions>
      <a-button @click="showAdd = true">+ 手动添加</a-button>
      <a-button :loading="reindexing" @click="onReindex">{{ reindexing ? '重建中…' : '重建向量索引' }}</a-button>
      <a-popconfirm title="确认清空所有记忆？" @confirm="onClearAll">
        <a-button danger>清空全部</a-button>
      </a-popconfirm>
    </template>
  </PageHeader>

  <div class="page-content">
    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card"><div class="stat-label">记忆总数</div><div class="stat-value">{{ stats?.total || 0 }}</div></div>
      <div class="stat-card vec"><div class="stat-label">已向量化</div><div class="stat-value">{{ stats?.vectorized || 0 }}</div></div>
      <!-- Embedding 模式标识 -->
      <div class="stat-card embed-mode" :class="stats?.embedding?.mode">
        <div class="stat-label">{{ stats?.embedding?.mode === 'local' ? '🟢 本地模型' : stats?.embedding?.mode === 'api' ? '🔵 API 模式' : '⏳ 待初始化' }}</div>
        <div class="stat-value small">{{ stats?.embedding?.model?.split('/').pop() || '-' }}</div>
      </div>
      <div v-for="(meta, type) in stats?.by_type || {}" :key="type" class="stat-card mini">
        <div class="stat-label">{{ typeMeta[type]?.label || type }}</div>
        <div class="stat-value small">{{ meta }}</div>
      </div>
    </div>

    <!-- 语义搜索 -->
    <div class="search-bar">
      <a-input-search
        v-model:value="searchQuery"
        placeholder="输入自然语言语义搜索记忆（如「主角第一次见到反派」「关键的背叛」）"
        enter-button="语义搜索"
        size="large"
        :loading="searching"
        @search="onSearch"
      />
      <a-button v-if="searchResults" type="link" @click="clearSearch">清除搜索结果</a-button>
    </div>

    <!-- 类型筛选 -->
    <div class="filter-bar">
      <a-checkable-tag :checked="!filterType" @change="filterType = ''">全部</a-checkable-tag>
      <a-checkable-tag
        v-for="(meta, type) in typeMeta"
        :key="type"
        :checked="filterType === type"
        @change="filterType = type"
      >{{ meta.label }}</a-checkable-tag>
    </div>

    <!-- 记忆列表 -->
    <div v-if="displayList.length" class="memory-list">
      <a-card v-for="m in displayList" :key="m.id || m.memory_id" hoverable size="small" class="memory-card">
        <div class="mem-head">
          <a-tag :color="typeMeta[m.memory_type]?.color || 'default'">{{ typeMeta[m.memory_type]?.label || m.memory_type }}</a-tag>
          <span v-if="m.title" class="mem-title">{{ m.title }}</span>
          <span v-if="m.chapter_number" class="mem-chap">第 {{ m.chapter_number }} 章</span>
          <span v-if="m.has_vector" class="vec-badge" title="已向量化">● 向量</span>
          <span v-if="m.similarity !== undefined" class="sim-badge">相似度 {{ (m.similarity * 100).toFixed(0) }}%</span>
          <div class="mem-actions">
            <a-button v-if="m.id" type="link" size="small" danger @click="onDelete(m.id)">删除</a-button>
          </div>
        </div>
        <div class="mem-content">{{ m.content }}</div>
        <div class="mem-foot">
          <span class="importance-bar">
            <span class="imp-label">重要度</span>
            <span class="imp-track"><span class="imp-fill" :style="{ width: (m.importance * 100) + '%', background: importanceColor(m.importance) }"></span></span>
            <span class="imp-num" :style="{ color: importanceColor(m.importance) }">{{ (m.importance * 100).toFixed(0) }}%</span>
          </span>
        </div>
      </a-card>
    </div>
    <a-empty v-else :description="searchResults ? '未找到相关记忆' : '暂无记忆，章节生成后会自动提取'" />

    <!-- 手动添加弹窗 -->
    <a-modal v-model:open="showAdd" title="手动添加记忆" width="520px">
      <a-form layout="vertical">
        <a-form-item label="类型">
          <a-select v-model:value="newMemory.memory_type">
            <a-select-option v-for="(meta, type) in typeMeta" :key="type" :value="type">{{ meta.label }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="标题（可选）"><a-input v-model:value="newMemory.title" /></a-form-item>
        <a-form-item label="章节号（可选）"><a-input-number v-model:value="newMemory.chapter_number" :min="1" style="width: 100%" /></a-form-item>
        <a-form-item label="内容"><a-textarea v-model:value="newMemory.content" :rows="4" /></a-form-item>
        <a-form-item label="重要度">
          <a-slider v-model:value="newMemory.importance" :min="0" :max="1" :step="0.05" :marks="{ 0: '0', 0.5: '中', 1: '高' }" />
        </a-form-item>
      </a-form>
      <template #footer>
        <a-button @click="showAdd = false">取消</a-button>
        <a-button type="primary" @click="onAdd">添加</a-button>
      </template>
    </a-modal>
  </div>
</template>

<style scoped>
.stats-row { display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
.stat-card { background: #fff; border: 1px solid #e8e8e8; border-radius: 8px; padding: 12px 16px; min-width: 110px; position: relative; overflow: hidden; }
.stat-card::before { content: ''; position: absolute; top: 0; left: 0; width: 3px; height: 100%; background: #4D8088; }
.stat-card.vec::before { background: #722ed1; }
.stat-card.mini::before { background: #B5C7CB; }
.stat-card.embed-mode::before { background: #52A569; }
.stat-card.embed-mode.api::before { background: #1677FF; }
.stat-card.embed-mode.uninitialized::before { background: #D49A4E; }
.stat-label { font-size: 11px; color: #8C8C8C; margin-bottom: 4px; }
.stat-value { font-size: 22px; font-weight: 600; color: #2B2B2B; }
.stat-value.small { font-size: 16px; }
.search-bar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.filter-bar { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; }
.memory-list { display: flex; flex-direction: column; gap: 10px; }
.memory-card { border-left: 3px solid #4D8088 !important; }
.mem-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.mem-title { font-weight: 600; color: #2B2B2B; font-size: 14px; }
.mem-chap { font-size: 12px; color: #8C8C8C; background: #F8F6F1; padding: 1px 6px; border-radius: 4px; }
.vec-badge { font-size: 10px; color: #722ed1; }
.sim-badge { font-size: 11px; color: #4D8088; background: #EAF0F1; padding: 1px 6px; border-radius: 4px; font-weight: 600; }
.mem-actions { margin-left: auto; }
.mem-content { font-size: 13px; color: #595959; line-height: 1.7; margin-bottom: 8px; }
.mem-foot { display: flex; align-items: center; }
.importance-bar { display: flex; align-items: center; gap: 6px; font-size: 11px; }
.imp-label { color: #8C8C8C; }
.imp-track { width: 100px; height: 4px; background: #F0EDE6; border-radius: 999; overflow: hidden; }
.imp-fill { height: 100%; border-radius: 999; }
.imp-num { font-weight: 600; }
</style>
