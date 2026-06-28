<script setup lang="ts">
// 地点/地图管理：树形结构 + 卡片 + AI 生成 + CRUD
import { API } from '~/composables/api'
import { useProject } from '~/composables/useProject'
useHead({ title: '地点地图 — 墨语' })
const { currentProjectId } = useProject()
if (!currentProjectId.value) await navigateTo('/books')
const msg = useMessage()
const { data: tree, refresh: refresh } = await useFetch<any[]>(() => `/api/projects/${currentProjectId.value}/locations/tree`)

const generating = ref(false)
const showAdd = ref(false)
const showGen = ref(false)
const genCount = ref(5)
const genType = ref('')
const genReq = ref('')
const genParentId = ref<number | null>(null)
const genParentName = ref('')
const editing = ref<any>(null)
const form = reactive({
  id: 0, name: '', location_type: '城市', parent_location_id: null as number | null,
  description: '', atmosphere: '', faction_control: '', geography: '',
  importance: 'normal', first_appear_chapter: null as number | null, danger_level: 'safe',
})

const typeList = ['城市', '区域', '建筑', '秘境', '自然景观', '国家', '大陆', '枢纽空间', '其他']
const importanceMeta: Record<string, { label: string; color: string }> = {
  minor: { label: '次要', color: 'default' },
  normal: { label: '普通', color: 'blue' },
  major: { label: '重要', color: 'orange' },
  key: { label: '关键', color: 'red' },
}
const dangerMeta: Record<string, { label: string; color: string }> = {
  safe: { label: '安全', color: 'success' },
  dangerous: { label: '危险', color: 'warning' },
  forbidden: { label: '禁区', color: 'error' },
  unknown: { label: '未知', color: 'default' },
}

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

async function onGenerate() {
  genParentId.value = null
  genParentName.value = ''
  genCount.value = 5
  genType.value = ''
  genReq.value = ''
  showGen.value = true
}
function openGenSub(parent: any) {
  genParentId.value = parent.id
  genParentName.value = parent.name
  genCount.value = 3
  genType.value = ''
  genReq.value = ''
  showGen.value = true
}
async function doGenerate() {
  generating.value = true
  try {
    const params: any = { count: genCount.value, location_type: genType.value, user_prompt: genReq.value }
    if (genParentId.value) params.parent_location_id = genParentId.value
    const r = await API.location.generate(params)
    await refresh()
    showGen.value = false
    msg.success(`生成 ${r.count} 个${genParentId.value ? '子' : ''}地点`)
  } catch (e: any) { msg.error('生成失败：' + formatError(e)) }
  finally { generating.value = false }
}
function openAdd(parent?: any) {
  editing.value = null
  Object.assign(form, { id: 0, name: '', location_type: '城市', parent_location_id: parent?.id || null, description: '', atmosphere: '', faction_control: '', geography: '', importance: 'normal', first_appear_chapter: null, danger_level: 'safe' })
  showAdd.value = true
}
function openEdit(l: any) {
  editing.value = l
  Object.assign(form, { ...l })
  showAdd.value = true
}
async function onSave() {
  if (!form.name.trim()) return
  try {
    if (editing.value) await API.location.update(form.id, { ...form })
    else await API.location.create({ ...form })
    showAdd.value = false
    await refresh()
    msg.success(editing.value ? '已更新' : '已添加')
  } catch (e: any) { msg.error('保存失败：' + formatError(e)) }
}
async function onDelete(id: number) {
  if (!await msg.confirm('确认删除？子地点将提升为顶级。')) return
  try { await API.location.delete(id); await refresh(); msg.success('已删除') }
  catch (e: any) { msg.error('删除失败：' + formatError(e)) }
}
</script>

<template>
  <PageHeader title="地点地图">
    <template #actions>
      <a-button @click="openAdd()">+ 添加地点</a-button>
      <a-button type="primary" :loading="generating" @click="onGenerate">{{ generating ? '生成中…' : ((tree||[]).length ? '➕ 追加生成' : 'AI 生成地点') }}</a-button>
    </template>
  </PageHeader>

  <div class="page-content">
    <a-alert v-if="!(tree && tree.length)" message="暂无地点，点击「AI 生成地点」开始" type="info" show-icon />
    <div v-else class="loc-list">
      <div v-for="l in flatList" :key="l.id" class="loc-row" :style="{ marginLeft: (l._level * 24) + 'px' }">
        <span v-if="l.children?.length" class="toggle-btn" @click="toggle(l.id)">
          {{ expanded.has(l.id) ? '▼' : '▶' }}
        </span>
        <span v-else class="toggle-btn placeholder"></span>
        <a-card size="small" class="loc-card" :class="`imp-${l.importance}`">
          <div class="loc-head">
            <span class="loc-icon">📍</span>
            <span class="loc-name">{{ l.name }}</span>
            <a-tag size="small" :color="importanceMeta[l.importance]?.color">{{ importanceMeta[l.importance]?.label }}</a-tag>
            <a-tag size="small">{{ l.location_type }}</a-tag>
            <a-tag v-if="l.danger_level !== 'safe'" size="small" :color="dangerMeta[l.danger_level]?.color">{{ dangerMeta[l.danger_level]?.label }}</a-tag>
            <span v-if="l.member_count || l.children?.length" class="meta-extra">
              <span v-if="l.children?.length">子地点 {{ l.children.length }}</span>
            </span>
            <div class="head-actions">
              <a-button type="link" size="small" @click="openAdd(l)">+ 子地点</a-button>
              <a-button type="link" size="small" @click="openGenSub(l)">🤖 AI 生成</a-button>
              <a-button type="link" size="small" @click="openEdit(l)">编辑</a-button>
              <a-button type="link" danger size="small" @click="onDelete(l.id)">删除</a-button>
            </div>
          </div>
          <div v-if="l.description" class="loc-desc">{{ l.description }}</div>
          <div class="loc-foot">
            <span v-if="l.atmosphere" class="foot-item">🌤 {{ l.atmosphere }}</span>
            <span v-if="l.faction_control" class="foot-item">⚔ {{ l.faction_control }}</span>
            <span v-if="l.first_appear_chapter" class="foot-item">📖 第{{ l.first_appear_chapter }}章</span>
          </div>
        </a-card>
      </div>
    </div>

    <a-modal v-model:open="showAdd" :title="editing ? '编辑地点' : '添加地点'" width="560px">
      <a-form layout="vertical">
        <a-form-item label="名称"><a-input v-model:value="form.name" /></a-form-item>
        <div class="form-row2">
          <a-form-item label="类型">
            <a-select v-model:value="form.location_type">
              <a-select-option v-for="t in typeList" :key="t" :value="t">{{ t }}</a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="重要性">
            <a-select v-model:value="form.importance">
              <a-select-option v-for="(m, k) in importanceMeta" :key="k" :value="k">{{ m.label }}</a-select-option>
            </a-select>
          </a-form-item>
        </div>
        <a-form-item label="描述"><a-textarea v-model:value="form.description" :rows="3" /></a-form-item>
        <div class="form-row2">
          <a-form-item label="氛围特色"><a-input v-model:value="form.atmosphere" placeholder="繁华喧嚣/阴森诡异..." /></a-form-item>
          <a-form-item label="控制势力"><a-input v-model:value="form.faction_control" /></a-form-item>
        </div>
        <div class="form-row2">
          <a-form-item label="地理特征"><a-input v-model:value="form.geography" /></a-form-item>
          <a-form-item label="危险等级">
            <a-select v-model:value="form.danger_level">
              <a-select-option v-for="(m, k) in dangerMeta" :key="k" :value="k">{{ m.label }}</a-select-option>
            </a-select>
          </a-form-item>
        </div>
        <a-form-item label="首次出现章节"><a-input-number v-model:value="form.first_appear_chapter" :min="1" style="width:100%" /></a-form-item>
      </a-form>
      <template #footer>
        <a-button @click="showAdd = false">取消</a-button>
        <a-button type="primary" @click="onSave">保存</a-button>
      </template>
    </a-modal>

    <!-- AI 生成地点弹窗 -->
    <a-modal v-model:open="showGen" :title="genParentId ? `AI 生成子地点（${genParentName}）` : ((tree||[]).length ? '追加生成地点' : 'AI 生成地点')" width="460px">
      <a-alert
        v-if="genParentId"
        :message="`将为「${genParentName}」生成子地点，AI 会参考父级地点的描述和氛围。`"
        type="info" show-icon :closable="false" style="margin-bottom:12px"
      />
      <a-alert
        v-else-if="(tree||[]).length"
        message="已有地点将保留，本次为追加生成（不覆盖）。AI 会避开已有的地点。"
        type="info" show-icon :closable="false" style="margin-bottom:12px"
      />
      <a-form layout="vertical">
        <a-form-item label="生成数量">
          <a-input-number v-model:value="genCount" :min="1" :max="10" style="width:100%" />
        </a-form-item>
        <a-form-item label="地点类型">
          <a-select v-model:value="genType" allow-clear placeholder="全部类型">
            <a-select-option value="">全部类型</a-select-option>
            <a-select-option v-for="t in typeList" :key="t" :value="t">{{ t }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="额外需求（可选）">
          <a-textarea v-model:value="genReq" :rows="2" placeholder="如：需要一个修仙宗门所在地、需要几个危险的禁地..." />
        </a-form-item>
      </a-form>
      <template #footer>
        <a-button @click="showGen = false">取消</a-button>
        <a-button type="primary" :loading="generating" @click="doGenerate">{{ generating ? '生成中…' : '开始生成' }}</a-button>
      </template>
    </a-modal>
  </div>
</template>

<style scoped>
.loc-list { display: flex; flex-direction: column; gap: 8px; }
.loc-row { display: flex; gap: 8px; align-items: flex-start; }
.toggle-btn { width: 20px; cursor: pointer; font-size: 12px; color: #8C8C8C; padding-top: 12px; text-align: center; user-select: none; }
.toggle-btn.placeholder { cursor: default; }
.loc-card { flex: 1; border-left: 3px solid #B5C7CB !important; }
.loc-card.imp-major { border-left-color: #D49A4E !important; }
.loc-card.imp-key { border-left-color: #C75B5B !important; }
.loc-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.loc-icon { font-size: 14px; }
.loc-name { font-size: 15px; font-weight: 600; }
.meta-extra { font-size: 11px; color: #8C8C8C; }
.head-actions { margin-left: auto; display: flex; }
.loc-desc { font-size: 13px; color: #595959; line-height: 1.6; margin: 8px 0; }
.loc-foot { display: flex; gap: 12px; font-size: 12px; color: #8C8C8C; flex-wrap: wrap; }
.form-row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
</style>
