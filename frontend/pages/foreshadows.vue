<script setup lang="ts">
// 伏笔管理：统计卡片 + 筛选栏 + 表格视图（对标参考站）
import { useProjectApi } from '~/composables/useProjectApi'
import { useProject } from '~/composables/useProject'
useHead({ title: '伏笔管理 — 墨语' })
const { currentProjectId } = useProject()
if (!currentProjectId.value) await navigateTo('/books')
const api = useProjectApi()
const msg = useMessage()
const { data: foreshadows, refresh } = await api.getForeshadows()

const generating = ref(false)
const showAdd = ref(false)
const editItem = ref<any>(null)
const form = reactive({
  id: 0, title: '', content: '', foreshadow_type: '主线', status: 'pending',
  plant_chapter_number: null as number | null,
  target_resolve_chapter_number: null as number | null,
  resolve_chapter_number: null as number | null,
  priority: 5,
})

// 状态映射
const statusMap: Record<string, { label: string; color: string }> = {
  pending: { label: '待埋设', color: 'warning' },
  planted: { label: '已埋设', color: 'processing' },
  resolving: { label: '回收中', color: 'default' },
  resolved: { label: '已回收', color: 'success' },
  abandoned: { label: '已废弃', color: 'default' },
}

// 类型映射
const typeMap: Record<string, { label: string; color: string }> = {
  主线: { label: '主线', color: 'red' },
  支线: { label: '支线', color: 'blue' },
  彩蛋: { label: '彩蛋', color: 'gold' },
  反转: { label: '反转', color: 'purple' },
}

// 统计卡片
const stats = computed(() => {
  const list = foreshadows.value || []
  const total = list.length
  const planted = list.filter((f: any) => ['planted', 'resolving', 'resolved'].includes(f.status)).length
  const resolved = list.filter((f: any) => f.status === 'resolved').length
  // 长线伏笔：跨度 >= 10 章或标注为主线
  const longTerm = list.filter((f: any) => {
    const span = (f.target_resolve_chapter_number || 0) - (f.plant_chapter_number || 0)
    return f.foreshadow_type === '主线' || span >= 10
  }).length
  return { total, planted, resolved, longTerm }
})

// 筛选
const filterStatus = ref('')
const filterType = ref('')
const filterKeyword = ref('')

async function onPlan() {
  if (!await msg.confirm('AI 将根据已有大纲自动规划伏笔（主线/支线/彩蛋/反转），已有伏笔不受影响。确认开始？')) return
  generating.value = true
  try {
    const r = await api.planForeshadows()
    await refresh()
    msg.success(`AI 规划完成，生成 ${r.count} 条伏笔`)
  } catch (e: any) {
    msg.error('规划失败：' + formatError(e))
  } finally {
    generating.value = false
  }
}

function openAdd() {
  editItem.value = null
  Object.assign(form, {
    id: 0, title: '', content: '', foreshadow_type: '主线', status: 'pending',
    plant_chapter_number: null, target_resolve_chapter_number: null,
    resolve_chapter_number: null, priority: 5,
  })
  showAdd.value = true
}
function openEdit(f: any) {
  editItem.value = f
  Object.assign(form, { ...f })
  showAdd.value = true
}
async function onSave() {
  try {
    if (editItem.value) await api.updateForeshadow(form.id, { ...form })
    else await api.createForeshadow({ ...form })
    showAdd.value = false
    await refresh()
    msg.success(editItem.value ? '已更新' : '已添加')
  } catch (e: any) {
    msg.error('保存失败：' + formatError(e))
  }
}
async function onDelete(id: number) {
  if (!await msg.confirm('确认删除？')) return
  try { await api.deleteForeshadow(id); await refresh(); msg.success('已删除') }
  catch (e: any) { msg.error('删除失败：' + formatError(e)) }
}

// ===== #15 伏笔闭环操作 =====
const showChapterPrompt = ref(false)
const promptAction = ref<'plant' | 'resolve' | 'abandon'>('plant')
const promptTarget = ref<any>(null)
const promptChapter = ref<number | null>(null)
const promptText = ref('')
const promptIsPartial = ref(false)

function onPlant(record: any) {
  promptAction.value = 'plant'
  promptTarget.value = record
  promptChapter.value = record.actual_plant_chapter || null
  promptText.value = ''
  showChapterPrompt.value = true
}
function onResolve(record: any, isPartial: boolean) {
  promptAction.value = 'resolve'
  promptTarget.value = record
  promptChapter.value = record.target_resolve_chapter_number || null
  promptText.value = ''
  promptIsPartial.value = isPartial
  showChapterPrompt.value = true
}
function onAbandon(record: any) {
  promptAction.value = 'abandon'
  promptTarget.value = record
  promptText.value = ''
  showChapterPrompt.value = true
}
async function onConfirmPrompt() {
  const rec = promptTarget.value
  if (!rec) return
  try {
    if (promptAction.value === 'plant') {
      await api.plantForeshadow(rec.id, promptChapter.value || 1, promptText.value)
      msg.success('已标记为已埋入')
    } else if (promptAction.value === 'resolve') {
      await api.resolveForeshadow(rec.id, promptChapter.value || 1, promptText.value, promptIsPartial.value)
      msg.success('已标记为已回收')
    } else {
      await api.abandonForeshadow(rec.id, promptText.value)
      msg.success('已放弃')
    }
    showChapterPrompt.value = false
    await refresh()
  } catch (e: any) { msg.error('操作失败：' + formatError(e)) }
}
async function onSyncFromAnalysis() {
  try {
    const r = await api.syncForeshadowsFromAnalysis()
    await refresh()
    msg.success(`已从分析同步：埋入 ${r.planted}，回收 ${r.resolved}`)
  } catch (e: any) { msg.error('同步失败：' + formatError(e)) }
}

// 表格列
const columns = [
  { title: '状态', dataIndex: 'status', key: 'status', width: 100, fixed: 'left' as const },
  { title: '标题', dataIndex: 'title', key: 'title', width: 180 },
  { title: '内容', dataIndex: 'content', key: 'content', ellipsis: true },
  { title: '分类', dataIndex: 'foreshadow_type', key: 'foreshadow_type', width: 90 },
  { title: '埋设章', dataIndex: 'plant_chapter_number', key: 'plant', width: 80, sorter: (a: any, b: any) => (a.plant_chapter_number || 9999) - (b.plant_chapter_number || 9999) },
  { title: '回收章', dataIndex: 'target_resolve_chapter_number', key: 'target', width: 80, sorter: (a: any, b: any) => (a.target_resolve_chapter_number || 9999) - (b.target_resolve_chapter_number || 9999) },
  { title: '重要性', dataIndex: 'priority', key: 'priority', width: 130, sorter: (a: any, b: any) => a.priority - b.priority },
  { title: '操作', key: 'actions', width: 200, fixed: 'right' as const },
]
const filteredData = computed(() => {
  let list = foreshadows.value || []
  if (filterStatus.value) list = list.filter((f: any) => f.status === filterStatus.value)
  if (filterType.value) list = list.filter((f: any) => f.foreshadow_type === filterType.value)
  if (filterKeyword.value.trim()) {
    const kw = filterKeyword.value.trim().toLowerCase()
    list = list.filter((f: any) =>
      (f.title || '').toLowerCase().includes(kw) || (f.content || '').toLowerCase().includes(kw),
    )
  }
  return list.map((f: any, i: number) => ({ ...f, key: f.id || i }))
})
</script>

<template>
  <PageHeader title="伏笔管理">
    <template #actions>
      <a-button @click="onSyncFromAnalysis">🔄 从分析同步</a-button>
      <a-button @click="openAdd">+ 手动添加</a-button>
      <a-button type="primary" :loading="generating" @click="onPlan">{{ generating ? 'AI 规划中…' : 'AI 规划伏笔' }}</a-button>
    </template>
  </PageHeader>

  <div class="page-content">
    <!-- 自动回收说明 -->
    <a-alert
      message="伏笔状态说明"
      description="伏笔状态会随章节剧情分析自动更新：分析检测到伏笔已埋入时自动标记「已埋设」，检测到伏笔已揭开时自动标记「已回收」。也可点击「从分析同步」手动触发。"
      type="info"
      show-icon
      closable
      style="margin-bottom:16px"
    />

    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-label">总数</div>
        <div class="stat-value">{{ stats.total }}</div>
      </div>
      <div class="stat-card planted">
        <div class="stat-label">已埋入</div>
        <div class="stat-value">{{ stats.planted }}</div>
      </div>
      <div class="stat-card resolved">
        <div class="stat-label">已回收</div>
        <div class="stat-value">{{ stats.resolved }}</div>
      </div>
      <div class="stat-card longterm">
        <div class="stat-label">长线伏笔</div>
        <div class="stat-value">{{ stats.longTerm }}</div>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <div class="filter-group">
        <span class="filter-label">状态：</span>
        <a-checkable-tag :checked="!filterStatus" @change="filterStatus = ''">全部</a-checkable-tag>
        <a-checkable-tag v-for="(v, k) in statusMap" :key="k" :checked="filterStatus === k" @change="filterStatus = k as string">{{ v.label }}</a-checkable-tag>
      </div>
      <div class="filter-group">
        <span class="filter-label">分类：</span>
        <a-checkable-tag :checked="!filterType" @change="filterType = ''">全部</a-checkable-tag>
        <a-checkable-tag v-for="(v, k) in typeMap" :key="k" :checked="filterType === k" @change="filterType = k as string">{{ v.label }}</a-checkable-tag>
      </div>
      <a-input-search v-model:value="filterKeyword" placeholder="搜索标题/内容" allow-clear style="width: 240px; margin-left: auto" />
    </div>

    <!-- 表格 -->
    <a-table
      v-if="filteredData.length"
      :columns="columns"
      :data-source="filteredData"
      :pagination="{ pageSize: 15, showSizeChanger: true }"
      size="middle"
      :scroll="{ x: 1000 }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'status'">
          <a-tag :color="statusMap[record.status]?.color || 'default'">
            {{ statusMap[record.status]?.label || record.status }}
          </a-tag>
        </template>
        <template v-else-if="column.key === 'foreshadow_type'">
          <a-tag :color="typeMap[record.foreshadow_type]?.color || 'default'">{{ record.foreshadow_type || '—' }}</a-tag>
        </template>
        <template v-else-if="column.key === 'plant'">
          {{ record.plant_chapter_number ? `第${record.plant_chapter_number}章` : '—' }}
        </template>
        <template v-else-if="column.key === 'target'">
          {{ record.target_resolve_chapter_number ? `第${record.target_resolve_chapter_number}章` : '—' }}
        </template>
        <template v-else-if="column.key === 'priority'">
          <a-rate :value="Math.ceil((record.priority || 0) / 2)" disabled :count="5" style="font-size: 12px" />
          <span class="priority-num">{{ record.priority }}/10</span>
        </template>
        <template v-else-if="column.key === 'actions'">
          <a-button v-if="record.status === 'pending'" type="link" size="small" style="color:#52A569" @click="onPlant(record)">埋设</a-button>
          <a-button v-if="record.status === 'planted' || record.status === 'partially_resolved'" type="link" size="small" style="color:#1677FF" @click="onResolve(record, false)">回收</a-button>
          <a-button v-if="record.status !== 'resolved' && record.status !== 'abandoned'" type="link" size="small" style="color:#8C8C8C" @click="onAbandon(record)">放弃</a-button>
          <a-button type="link" size="small" @click="openEdit(record)">编辑</a-button>
          <a-button type="link" danger size="small" @click="onDelete(record.id)">删除</a-button>
        </template>
      </template>
    </a-table>
    <a-empty v-else description="暂无伏笔。先生成大纲，再用 AI 自动规划伏笔" />
  </div>

  <!-- 添加/编辑弹窗 -->
  <a-modal v-model:open="showAdd" :title="editItem ? '编辑伏笔' : '添加伏笔'" width="560px">
    <a-form layout="vertical">
      <a-form-item label="标题">
        <a-input v-model:value="form.title" />
      </a-form-item>
      <a-form-item label="内容描述">
        <a-textarea v-model:value="form.content" :rows="3" />
      </a-form-item>
      <div class="form-row3">
        <a-form-item label="类型">
          <a-select v-model:value="form.foreshadow_type">
            <a-select-option v-for="(v, k) in typeMap" :key="k" :value="k">{{ v.label }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="状态">
          <a-select v-model:value="form.status">
            <a-select-option v-for="(v, k) in statusMap" :key="k" :value="k">{{ v.label }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="重要性">
          <a-input-number v-model:value="form.priority" :min="1" :max="10" style="width: 100%" />
        </a-form-item>
      </div>
      <div class="form-row2">
        <a-form-item label="埋设章节">
          <a-input-number v-model:value="form.plant_chapter_number" :min="1" style="width: 100%" />
        </a-form-item>
        <a-form-item label="目标回收章节">
          <a-input-number v-model:value="form.target_resolve_chapter_number" :min="1" style="width: 100%" />
        </a-form-item>
      </div>
    </a-form>
    <template #footer>
      <a-button @click="showAdd = false">取消</a-button>
      <a-button type="primary" @click="onSave">保存</a-button>
    </template>
  </a-modal>

  <!-- #15 伏笔闭环操作弹窗 -->
  <a-modal v-model:open="showChapterPrompt" :title="{plant:'埋设伏笔',resolve:'回收伏笔',abandon:'放弃伏笔'}[promptAction]" width="460px">
    <p style="margin-bottom:12px;color:#595959;">伏笔：<b>{{ promptTarget?.title }}</b></p>
    <a-form layout="vertical" v-if="promptAction !== 'abandon'">
      <a-form-item label="章节号">
        <a-input-number v-model:value="promptChapter" :min="1" style="width:100%" />
      </a-form-item>
      <a-form-item :label="promptAction === 'plant' ? '埋入提示（可选）' : '回收说明（可选）'">
        <a-textarea v-model:value="promptText" :rows="2" />
      </a-form-item>
      <a-form-item v-if="promptAction === 'resolve'">
        <a-checkbox v-model:checked="promptIsPartial">部分回收（伏笔仅部分揭开）</a-checkbox>
      </a-form-item>
    </a-form>
    <a-form layout="vertical" v-else>
      <a-form-item label="放弃原因（可选）">
        <a-textarea v-model:value="promptText" :rows="3" placeholder="如：剧情调整，此伏笔不再需要" />
      </a-form-item>
    </a-form>
    <template #footer>
      <a-button @click="showChapterPrompt = false">取消</a-button>
      <a-button type="primary" @click="onConfirmPrompt">确认</a-button>
    </template>
  </a-modal>
</template>

<style scoped>
.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
.stat-card { background: #fff; border: 1px solid #e8e8e8; border-radius: 8px; padding: 16px; position: relative; overflow: hidden; }
.stat-card::before { content: ''; position: absolute; top: 0; left: 0; width: 4px; height: 100%; background: #8C8C8C; }
.stat-card.planted::before { background: #1677ff; }
.stat-card.resolved::before { background: #52c41a; }
.stat-card.longterm::before { background: #722ed1; }
.stat-label { font-size: 12px; color: #8C8C8C; margin-bottom: 6px; }
.stat-value { font-size: 26px; font-weight: 600; color: #2B2B2B; }
.filter-bar { display: flex; gap: 20px; align-items: center; flex-wrap: wrap; margin-bottom: 16px; padding: 12px; background: #FAFAFA; border-radius: 6px; }
.filter-group { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.filter-label { font-size: 12px; color: #8C8C8C; }
.priority-num { font-size: 11px; color: #8C8C8C; margin-left: 4px; }
.form-row3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
.form-row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
</style>
