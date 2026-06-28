<script setup lang="ts">
// 世界设定：对标参考站 — 基础信息卡 + 世界观卡 + 详细设定卡（标签+值描述列表）
import { useBookApi } from '~/composables/useBookApi'
import { useProject } from '~/composables/useProject'
useHead({ title: '世界设定 — 墨语' })
const { currentProjectId, currentProjectInfo } = useProject()
if (!currentProjectId.value) await navigateTo('/books')
const api = useBookApi()
const msg = useMessage()
const { data: project, refresh: refreshProject } = await useFetch(() => `/projects/${currentProjectId.value}`)
const { data: worlds, refresh: refreshWorlds } = await useFetch(() => `/projects/${currentProjectId.value}/worldview`)
const { data: worldCore, refresh: refreshCore } = await useFetch(() => `/projects/${currentProjectId.value}/worldview/core`)

const genAll = ref(false)
const reindexingWorlds = ref(false)
const editingCore = ref(false)
const editingBasic = ref(false)
const basicForm = reactive({ title:'', synopsis:'', genre:'', narrative_pov:'', target_word_count:100000 })
const genres = ['玄幻','都市','科幻','言情','历史','武侠','游戏','悬疑','其他']

function openEditBasic() {
  const p = project.value || {}
  Object.assign(basicForm, { title:p.title||'', synopsis:p.synopsis||'', genre:p.genre||'', narrative_pov:p.narrative_pov||'第三人称', target_word_count:p.target_word_count ?? 100000 })
  editingBasic.value = true
}
async function onSaveBasic() {
  try { await api.updateProject({ ...basicForm }); await refreshProject(); editingBasic.value = false; msg.success('已保存') }
  catch (e:any) { msg.error('保存失败：'+formatError(e)) }
}
const coreForm = reactive({ world_time_period: '', world_location: '', world_atmosphere: '', world_rules: '' })
const coreFields = [
  { key: 'world_time_period', label: '时间设定' },
  { key: 'world_location', label: '地点设定' },
  { key: 'world_atmosphere', label: '氛围设定' },
  { key: 'world_rules', label: '规则设定' },
]
const editingDetail = ref<any>(null)
const detailForm = reactive({ name: '', category: '其他', content: '' })
const categories = ['地理', '历史', '种族', '势力', '修炼体系', '科技', '文化', '经济', '军事', '宗教', '风俗',
  '系统空间', '位面分类', '常见位面模板', '穿越者组织', '任务机制', '积分兑换', '规则边界', '位面意志', '身份生成', '异常事件',
  '世界基线', '关键节点', '循环变量', '记忆继承', '蝴蝶效应案例', '终局路径',
  '表世界地理', '里世界地理', '边界与通道', '双世界交互规则', '两边势力对照',
  '其他']

async function onGenCore() {
  if (!await msg.confirm('AI 将重新生成核心世界观（时间/地点/氛围/规则），已有内容将被覆盖。确认开始？')) return
  genAll.value = true
  try { await api.generateWorldCore(); await refreshCore(); msg.success('核心世界观已生成') }
  catch (e: any) { msg.error('生成失败：' + formatError(e)) }
  finally { genAll.value = false }
}
async function onGenDetail() {
  if (!await msg.confirm('AI 将生成详细世界观设定条目（根据题材自适应类别），已有条目不受影响。确认开始？')) return
  genAll.value = true
  try {
    await api.generateWorld({ genre: currentProjectInfo.value?.genre || '', idea: (worldCore.value?.world_rules || '') + ' ' + (worldCore.value?.world_location || '') })
    await refreshWorlds(); msg.success('详细设定已生成')
  } catch (e: any) { msg.error('生成失败：' + formatError(e)) }
  finally { genAll.value = false }
}
function openEditCore() {
  const c = worldCore.value || {}
  Object.assign(coreForm, { world_time_period: c.world_time_period||'', world_location: c.world_location||'', world_atmosphere: c.world_atmosphere||'', world_rules: c.world_rules||'' })
  editingCore.value = true
}
async function onSaveCore() {
  try { await api.updateWorldCore({ ...coreForm }); await refreshCore(); editingCore.value = false; msg.success('已保存') }
  catch (e: any) { msg.error('保存失败：' + formatError(e)) }
}
function openEditDetail(w: any) { editingDetail.value = w; Object.assign(detailForm, { name: w.name, category: w.category||'其他', content: w.content||'' }) }
async function onSaveDetail() {
  try { await api.updateWorld(editingDetail.value.id, { ...detailForm, structure: {} }); await refreshWorlds(); editingDetail.value = null; msg.success('已保存') }
  catch (e: any) { msg.error('保存失败：' + formatError(e)) }
}
async function onDeleteDetail(id: number) {
  if (!await msg.confirm('确认删除？')) return
  try { await api.deleteWorld(id); await refreshWorlds(); msg.success('已删除') }
  catch (e: any) { msg.error('删除失败：' + formatError(e)) }
}
const showAdd = ref(false)
const newWorld = reactive({ name: '', category: '地理', content: '' })
async function onAdd() {
  if (!newWorld.name.trim()) return
  try { await api.createWorld({ ...newWorld }); showAdd.value = false; newWorld.name=''; newWorld.content=''; await refreshWorlds() }
  catch (e: any) { msg.error('添加失败：' + formatError(e)) }
}
async function onReindexWorldVectors() {
  reindexingWorlds.value = true
  try {
    const r = await api.reindexWorldVectors()
    msg.success(r.message || `已提交 ${r.total} 条数据的向量同步`)
  } catch (e: any) { msg.error('同步失败：' + formatError(e)) }
  finally { reindexingWorlds.value = false }
}
</script>

<template>
  <div class="world-page">
    <div class="page-actions">
      <a-button @click="openEditBasic">编辑基础信息</a-button>
      <a-button :loading="reindexingWorlds" @click="onReindexWorldVectors">🔄 回填向量索引</a-button>
      <a-button :loading="genAll" @click="onGenCore">AI 重新生成世界观</a-button>
      <a-button @click="openEditCore">编辑世界观</a-button>
      <a-button @click="onGenDetail" :loading="genAll">AI 生成详细设定</a-button>
      <a-button @click="showAdd = true">+ 添加条目</a-button>
    </div>

    <!-- 基础信息卡 -->
    <a-card title="基础信息" size="small" class="info-card">
      <a-descriptions :column="2" size="small" bordered>
        <a-descriptions-item label="小说名称" :span="2">{{ project?.title || '未命名' }}</a-descriptions-item>
        <a-descriptions-item label="小说简介" :span="2">{{ project?.synopsis || '暂无' }}</a-descriptions-item>
        <a-descriptions-item label="小说类型">{{ project?.genre || '未分类' }}</a-descriptions-item>
        <a-descriptions-item label="叙事视角">{{ project?.narrative_pov || '第三人称' }}</a-descriptions-item>
        <a-descriptions-item label="目标字数">{{ (project?.target_word_count || 0).toLocaleString() }} 字</a-descriptions-item>
        <a-descriptions-item label="当前字数">{{ (project?.current_word_count || 0).toLocaleString() }} 字</a-descriptions-item>
      </a-descriptions>
    </a-card>

    <!-- 世界观卡 -->
    <a-card title="小说世界观" size="small" class="info-card">
      <a-descriptions :column="1" size="small" bordered>
        <a-descriptions-item v-for="f in coreFields" :key="f.key" :label="f.label">
          <span :class="{ empty: !worldCore?.[f.key] }">{{ worldCore?.[f.key] || '未设定' }}</span>
        </a-descriptions-item>
      </a-descriptions>
    </a-card>

    <!-- 详细设定卡 -->
    <a-card size="small" class="info-card">
      <template #title>详细设定 <a-tag>{{ (worlds||[]).length }} 条</a-tag></template>
      <div v-if="worlds && worlds.length" class="detail-list">
        <div v-for="w in worlds" :key="w.id" class="detail-item">
          <div class="detail-item-head">
            <a-tag color="blue" size="small">{{ w.category || '其他' }}</a-tag>
            <span class="detail-name">{{ w.name }}</span>
            <div class="detail-item-actions">
              <a-button type="link" size="small" @click="openEditDetail(w)">编辑</a-button>
              <a-button type="link" danger size="small" @click="onDeleteDetail(w.id)">删除</a-button>
            </div>
          </div>
          <div class="detail-content">{{ w.content || '暂无描述' }}</div>
        </div>
      </div>
      <a-empty v-else description="暂无详细设定，点击「AI 生成详细设定」" />
    </a-card>

    <!-- 编辑基础信息 -->
    <a-modal v-model:open="editingBasic" title="编辑基础信息" width="560px">
      <a-form layout="vertical">
        <a-form-item label="书名" required><a-input v-model:value="basicForm.title" /></a-form-item>
        <a-form-item label="简介"><a-textarea v-model:value="basicForm.synopsis" :rows="3" /></a-form-item>
        <a-row :gutter="12">
          <a-col :span="12"><a-form-item label="类型"><a-select v-model:value="basicForm.genre" style="width:100%"><a-select-option v-for="g in genres" :key="g" :label="g" :value="g" /></a-select></a-form-item></a-col>
          <a-col :span="12"><a-form-item label="叙事视角"><a-select v-model:value="basicForm.narrative_pov" style="width:100%"><a-select-option label="第三人称" value="第三人称" /><a-select-option label="第一人称" value="第一人称" /><a-select-option label="全知视角" value="全知视角" /></a-select></a-form-item></a-col>
        </a-row>
        <a-form-item label="目标字数"><a-input-number v-model:value="basicForm.target_word_count" :min="10000" :max="5000000" :step="10000" style="width:100%" /> 字</a-form-item>
      </a-form>
      <template #footer><a-button @click="editingBasic=false">取消</a-button><a-button type="primary" @click="onSaveBasic">保存</a-button></template>
    </a-modal>

    <!-- 编辑核心世界观 -->
    <a-modal v-model:open="editingCore" title="编辑世界观" width="640px">
      <a-form layout="vertical">
        <a-form-item v-for="f in coreFields" :key="f.key" :label="f.label"><a-textarea v-model:value="coreForm[f.key]" :rows="3" /></a-form-item>
      </a-form>
      <template #footer><a-button @click="editingCore=false">取消</a-button><a-button type="primary" @click="onSaveCore">保存</a-button></template>
    </a-modal>
    <!-- 编辑详细设定 -->
    <a-modal :open="!!editingDetail" @update:open="(v:any)=>{if(!v)editingDetail=null}" title="编辑详细设定" width="500px" v-if="editingDetail">
      <a-form layout="vertical">
        <a-form-item label="名称"><a-input v-model:value="detailForm.name" /></a-form-item>
        <a-form-item label="分类"><a-select v-model:value="detailForm.category" style="width:100%"><a-select-option v-for="c in categories" :key="c" :label="c" :value="c" /></a-select></a-form-item>
        <a-form-item label="内容"><a-textarea v-model:value="detailForm.content" :rows="6" /></a-form-item>
      </a-form>
      <template #footer><a-button @click="editingDetail=null">取消</a-button><a-button type="primary" @click="onSaveDetail">保存</a-button></template>
    </a-modal>
    <!-- 添加 -->
    <a-modal v-model:open="showAdd" title="添加详细设定" width="500px">
      <a-form layout="vertical">
        <a-form-item label="名称"><a-input v-model:value="newWorld.name" /></a-form-item>
        <a-form-item label="分类"><a-select v-model:value="newWorld.category" style="width:100%"><a-select-option v-for="c in categories" :key="c" :label="c" :value="c" /></a-select></a-form-item>
        <a-form-item label="内容"><a-textarea v-model:value="newWorld.content" :rows="4" /></a-form-item>
      </a-form>
      <template #footer><a-button @click="showAdd=false">取消</a-button><a-button type="primary" @click="onAdd">添加</a-button></template>
    </a-modal>
  </div>
</template>

<style scoped>
.world-page { display: flex; flex-direction: column; gap: 16px; }
.page-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.info-card { }
.empty { color: #bbb; }
.detail-list { display: flex; flex-direction: column; gap: 12px; }
.detail-item { border: 1px solid #F0EDE6; border-radius: 8px; padding: 12px 16px; }
.detail-item-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.detail-name { font-weight: 600; color: #2B2B2B; }
.detail-item-actions { margin-left: auto; display: flex; gap: 2px; }
.detail-content { font-size: 14px; color: #595959; line-height: 1.7; white-space: pre-wrap; }
</style>
