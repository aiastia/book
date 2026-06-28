<script setup lang="ts">
// 伏笔管理：统计卡片 + 筛选栏 + 表格视图（对标参考站）
import { API } from '~/composables/api'
import { useProject } from '~/composables/useProject'
useHead({ title: '伏笔管理 — 墨语' })
const { currentProjectId } = useProject()
if (!currentProjectId.value) await navigateTo('/books')
const msg = useMessage()
const { data: foreshadows, refresh: refresh } = await useFetch(() => `/projects/${currentProjectId.value}/foreshadows`)

const generating = ref(false)
const showAdd = ref(false)
const editItem = ref<any>(null)
const form = reactive({
  id: 0, title: '', content: '', foreshadow_type: '主线', status: 'pending',
  plant_chapter_number: null as number | null,
  target_resolve_chapter_number: null as number | null,
  resolve_chapter_number: null as number | null,
  priority: 5,
  // 扩展字段（存 structure JSON）
  importance: 0.7,
  strength: 5,
  concealment: 7,
  is_long_term: false,
  hint_text: '',
  notes: '',
  related_characters: [] as string[],
  auto_remind: true,
  include_in_context: true,
  remind_before_chapters: 3,
})
const characterOptions = ref<Array<{ name: string; role: string; label: string }>>([])

// 加载角色候选
async function loadCharacterOptions() {
  try {
    const res = await useFetch(() => `/api/projects/${currentProjectId.value}/characters`)
    const list = (res as any).data || (res as any) || []
    characterOptions.value = list.map(c => ({ name: c.name, role: c.role || '', label: c.role ? `${c.name}（${c.role}）` : c.name }))
  } catch (e) { console.warn('加载角色失败', e) }
}

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

// 来源映射
const sourceMap: Record<string, { label: string; color: string }> = {
  planned: { label: 'AI 规划', color: 'blue' },
  analysis: { label: '分析发现', color: 'green' },
  manual: { label: '手动', color: 'default' },
}

// 统计卡片
const stats = computed(() => {
  const list = foreshadows.value || []
  const total = list.length
  const planted = list.filter((f: any) => ['planted', 'resolving', 'resolved'].includes(f.status)).length
  const resolved = list.filter((f: any) => f.status === 'resolved').length
  // 长线伏笔：标注为 is_long_term = true
  const longTerm = list.filter((f: any) => {
    return (f.structure?.is_long_term) || f.foreshadow_type === '主线'
  }).length
  return { total, planted, resolved, longTerm }
})

// 筛选
const filterStatus = ref('')
const filterType = ref('')
const filterKeyword = ref('')
const selectedRowKeys = ref<number[]>([])
const hasSelected = computed(() => selectedRowKeys.value.length > 0)

async function onDelete(id: number) {
  if (!await msg.confirm('确认删除此伏笔？')) return
  try { await API.foreshadow.delete(id); await refresh(); msg.success('已删除') }
  catch (e: any) { msg.error('删除失败：' + formatError(e)) }
}

async function onBatchDelete() {
  if (!selectedRowKeys.value.length) return
  if (!await msg.confirm(`确认删除选中的 ${selectedRowKeys.value.length} 条伏笔？`)) return
  try {
    const res = await API.foreshadow.batchDelete(selectedRowKeys.value)
    msg.success(`已删除 ${res.deleted} 条`)
    selectedRowKeys.value = []
    await refresh()
  } catch (e: any) { msg.error('批量删除失败：' + formatError(e)) }
}

async function onPlan() {
  if (!await msg.confirm('AI 将根据已有大纲自动规划伏笔（主线/支线/彩蛋/反转），已有伏笔不受影响。确认开始？')) return
  generating.value = true
  try {
    const r = await API.foreshadow.plan()
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
    importance: 0.7, strength: 5, concealment: 7, is_long_term: false,
    hint_text: '', notes: '', related_characters: [],
    auto_remind: true, include_in_context: true, remind_before_chapters: 3,
  })
  loadCharacterOptions()
  showAdd.value = true
}
function openEdit(f: any) {
  editItem.value = f
  const s = f.structure || {}
  Object.assign(form, {
    ...f,
    importance: s.importance ?? 0.7,
    strength: s.strength ?? 5,
    concealment: s.concealment ?? 7,
    is_long_term: s.is_long_term ?? false,
    hint_text: s.hint_text ?? '',
    notes: s.notes ?? '',
    related_characters: s.related_characters ?? [],
    auto_remind: s.auto_remind ?? true,
    include_in_context: s.include_in_context ?? true,
    remind_before_chapters: s.remind_before_chapters ?? 3,
  })
  loadCharacterOptions()
  showAdd.value = true
}
async function onSave() {
  try {
    const body: any = { ...form }
    // 把扩展字段打包进 structure
    body.structure = {
      importance: form.importance,
      strength: form.strength,
      concealment: form.concealment,
      is_long_term: form.is_long_term,
      hint_text: form.hint_text,
      notes: form.notes,
      related_characters: form.related_characters,
      auto_remind: form.auto_remind,
      include_in_context: form.include_in_context,
      remind_before_chapters: form.remind_before_chapters,
    }
    if (editItem.value) await API.foreshadow.update(form.id, body)
    else await API.foreshadow.create(body)
    showAdd.value = false
    await refresh()
    msg.success(editItem.value ? '已更新' : '已添加')
  } catch (e: any) {
    msg.error('保存失败：' + formatError(e))
  }
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
      await API.foreshadow.plant(rec.id, promptChapter.value || 1, promptText.value)
      msg.success('已标记为已埋入')
    } else if (promptAction.value === 'resolve') {
      await API.foreshadow.resolve(rec.id, promptChapter.value || 1, promptText.value, promptIsPartial.value)
      msg.success('已标记为已回收')
    } else {
      await API.foreshadow.abandon(rec.id, promptText.value)
      msg.success('已放弃')
    }
    showChapterPrompt.value = false
    await refresh()
  } catch (e: any) { msg.error('操作失败：' + formatError(e)) }
}
async function onSyncFromAnalysis() {
  try {
    const r = await API.chapter.syncForeshadows()
    await refresh()
    msg.success(`已从分析同步：埋入 ${r.planted}，回收 ${r.resolved}`)
  } catch (e: any) { msg.error('同步失败：' + formatError(e)) }
}

// 表格列
const columns = [
  { title: '状态', dataIndex: 'status', key: 'status', width: 100, fixed: 'left' as const },
  { title: '标题', dataIndex: 'title', key: 'title', width: 180 },
  { title: '内容', dataIndex: 'content', key: 'content', ellipsis: true, width: 200 },
  { title: '分类', dataIndex: 'foreshadow_type', key: 'foreshadow_type', width: 80 },
  { title: '来源', dataIndex: 'source_type', key: 'source', width: 90 },
  { title: '关联角色', dataIndex: 'related_characters', key: 'chars', width: 130 },
  { title: '埋设章', dataIndex: 'plant_chapter_number', key: 'plant', width: 80, sorter: (a: any, b: any) => (a.plant_chapter_number || 9999) - (b.plant_chapter_number || 9999) },
  { title: '计划回收章', dataIndex: 'target_resolve_chapter_number', key: 'target', width: 90, sorter: (a: any, b: any) => (a.target_resolve_chapter_number || 9999) - (b.target_resolve_chapter_number || 9999) },
  { title: '实际回收章', dataIndex: 'actual_resolve_chapter', key: 'actual_resolve', width: 90 },
  { title: '重要性', dataIndex: 'priority', key: 'priority', width: 120, sorter: (a: any, b: any) => a.priority - b.priority },
  { title: '操作', key: 'actions', width: 220, fixed: 'right' as const },
]
// 辅助: 从 record 拿到安全的结构体字段
function sField(rec: any, key: string, def: any = '') {
  return (rec.structure || {})[key] ?? def
}
function getRelatedChars(rec: any): string[] {
  const s = rec.structure || {}
  const r = s.related_characters || []
  return Array.isArray(r) ? r : []
}
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
      <a-button v-if="hasSelected" danger @click="onBatchDelete">🗑 删除选中（{{ selectedRowKeys.length }}）</a-button>
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
      :row-selection="{ selectedRowKeys, onChange: (keys: any) => selectedRowKeys = keys as number[] }"
      :pagination="{ pageSize: 15, showSizeChanger: true }"
      size="middle"
      :scroll="{ x: 1100 }"
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
        <template v-else-if="column.key === 'source'">
          <a-tag :color="sourceMap[record.source_type]?.color || 'default'">{{ sourceMap[record.source_type]?.label || record.source_type || '—' }}</a-tag>
        </template>
        <template v-else-if="column.key === 'plant'">
          {{ record.plant_chapter_number ? `第${record.plant_chapter_number}章` : '—' }}
        </template>
        <template v-else-if="column.key === 'target'">
          {{ record.target_resolve_chapter_number ? `第${record.target_resolve_chapter_number}章` : '—' }}
        </template>
        <template v-else-if="column.key === 'actual_resolve'">
          <span v-if="record.actual_resolve_chapter" style="color: #52A569; font-weight: 600">
            第{{ record.actual_resolve_chapter }}章
          </span>
          <span v-else style="color: #B5C7CB">—</span>
        </template>
        <template v-else-if="column.key === 'chars'">
          <template v-if="getRelatedChars(record).length">
            <a-tag v-for="(c, i) in getRelatedChars(record).slice(0, 2)" :key="i" color="purple" size="small" style="margin:1px">{{ c }}</a-tag>
            <a-tag v-if="getRelatedChars(record).length > 2" size="small" color="default">+{{ getRelatedChars(record).length - 2 }}</a-tag>
          </template>
          <span v-else style="color:#ccc">—</span>
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
  <a-modal v-model:open="showAdd" :title="editItem ? '编辑伏笔' : '添加伏笔'" width="680px" :destroy-on-close="true">
    <a-form layout="vertical" class="fs-form">
      <!-- 基础 -->
      <a-form-item label="标题"><a-input v-model:value="form.title" /></a-form-item>
      <a-form-item label="内容描述">
        <a-textarea v-model:value="form.content" :rows="3" placeholder="伏笔详细描述（至少30字）" />
      </a-form-item>

      <!-- 分类 + 状态 + 重要性 -->
      <a-row :gutter="12">
        <a-col :span="8">
          <a-form-item label="分类"><a-select v-model:value="form.foreshadow_type" :options="Object.entries(typeMap).map(([k,v])=>({value:k,label:v.label}))" /></a-form-item>
        </a-col>
        <a-col :span="8">
          <a-form-item label="状态"><a-select v-model:value="form.status" :options="Object.entries(statusMap).map(([k,v])=>({value:k,label:v.label}))" /></a-form-item>
        </a-col>
        <a-col :span="8">
          <a-form-item label="重要性 1-10" tooltip="结构重要性标尺：10=核心悬念, 7=重大转折, 5=支线线索, 3=章节呼应, 1=小彩蛋">
            <a-input-number v-model:value="form.priority" :min="1" :max="10" style="width:100%" />
          </a-form-item>
        </a-col>
      </a-row>

      <!-- 章节号 -->
      <a-row :gutter="12">
        <a-col :span="12">
          <a-form-item label="计划埋入章节"><a-input-number v-model:value="form.plant_chapter_number" :min="1" style="width:100%" /></a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="计划回收章节"><a-input-number v-model:value="form.target_resolve_chapter_number" :min="1" style="width:100%" /></a-form-item>
        </a-col>
      </a-row>

      <!-- 文学重要性 + 强度 + 隐藏度 -->
      <a-row :gutter="12">
        <a-col :span="8">
          <a-form-item label="文学重要性 0-1" tooltip="对主题/人物弧光的叙事价值。0.5=一般, 0.7=显著, 0.9+=核心主题级">
            <a-input-number v-model:value="form.importance" :min="0" :max="1" :step="0.05" style="width:100%" />
          </a-form-item>
        </a-col>
        <a-col :span="8">
          <a-form-item label="强度 1-10" tooltip="读者意识到的可能性。1=几乎不可察觉, 5=有心人能注意, 10=明显">
            <a-input-number v-model:value="form.strength" :min="1" :max="10" style="width:100%" />
          </a-form-item>
        </a-col>
        <a-col :span="8">
          <a-form-item label="隐藏度 1-10" tooltip="伏笔被掩盖的程度。10=完全藏于细节, 1=直接明示">
            <a-input-number v-model:value="form.concealment" :min="1" :max="10" style="width:100%" />
          </a-form-item>
        </a-col>
      </a-row>

      <!-- 关联角色 -->
      <a-form-item label="关联角色">
        <a-select v-model:value="form.related_characters" mode="tags" placeholder="选择或输入角色名，回车添加"
          :options="characterOptions.map(c => ({ value: c.name, label: c.label }))"
          option-filter-prop="label" :token-separators="[',', '，', '、']" style="width:100%" />
        <div class="field-hint">可从已有角色选择，也可直接输入新名字</div>
      </a-form-item>

      <!-- 暗示文本 -->
      <a-form-item label="暗示文本" tooltip="伏笔在正文中的具体暗示语句（1-2句话，可直接用于正文）">
        <a-textarea v-model:value="form.hint_text" :rows="2" placeholder="例：镜中的影像仅供参考，但当镜中人比你先微笑时，请立刻远离" />
      </a-form-item>

      <!-- 备注 -->
      <a-form-item label="备注">
        <a-textarea v-model:value="form.notes" :rows="2" placeholder="补充说明：设计意图、与主线的交汇点等" />
      </a-form-item>

      <!-- AI 辅助设置 -->
      <a-row :gutter="12">
        <a-col :span="6">
          <a-form-item label="长线伏笔"><a-switch v-model:checked="form.is_long_term" /></a-form-item>
        </a-col>
        <a-col :span="6">
          <a-form-item label="自动提醒"><a-switch v-model:checked="form.auto_remind" /></a-form-item>
        </a-col>
        <a-col :span="6">
          <a-form-item label="含在上下文"><a-switch v-model:checked="form.include_in_context" /></a-form-item>
        </a-col>
        <a-col :span="6">
          <a-form-item label="提前N章提醒">
            <a-input-number v-model:value="form.remind_before_chapters" :min="1" :max="10" style="width:100%" />
          </a-form-item>
        </a-col>
      </a-row>
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
.fs-form { max-height: 62vh; overflow-y: auto; padding-right: 4px; }
.field-hint { font-size: 11px; color: #999; margin-top: 2px; }
</style>
