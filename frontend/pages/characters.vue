<script setup lang="ts">
// 角色设定：对标参考站 — 卡片网格，每个角色内容平铺（描述列表风格）
import { useProjectApi } from '~/composables/useProjectApi'
import { useProject } from '~/composables/useProject'
import { apiGet } from '~/composables/useApi'
useHead({ title: '角色设定 — 墨语' })
const { currentProjectId } = useProject()
if (!currentProjectId.value) await navigateTo('/books')
const api = useProjectApi()
const msg = useMessage()
const { data: characters, refresh } = await api.getCharacters()
// 加载职业体系，供「职业」字段下拉使用
const { data: careers } = await api.getCareers()
// 加载组织列表，供「所属组织」字段下拉使用
const { data: organizations } = await api.getOrganizations()
const occupationOptions = computed(() => {
  const list = (careers.value || []).map((c: any) => c.name).filter(Boolean)
  // 去重
  return Array.from(new Set(list))
})
// 职业名映射（显示修炼阶段用，#19）
const careerNameById = (id: number) => {
  const c = (careers.value || []).find((x: any) => x.id === id)
  return c?.name || `职业#${id}`
}
// 组织名映射
const orgNameById = (id: number | null) => {
  if (!id) return ''
  const o = (organizations.value || []).find((x: any) => x.id === id)
  return o?.name || ''
}

const showGen = ref(false)
const genRole = ref('主角')
const genExtra = ref('')
const generating = ref(false)
const showBatch = ref(false)
const batchCount = ref(5)
const batchReq = ref('')
const batchLoading = ref(false)

const editing = ref<any>(null)
const editForm = reactive({
  name:'', role:'配角', gender:'', age:'', identity:'', occupation:'',
  appearance:'', personality:'', background:'', growth_experience:'', ability:'',
  story_goal:'', motivation:'', weakness:'', arc_type:'', character_change:'', speech_style:'',
  status:'alive', mental_state:'', organization_id: null as number | null,
})
const roleOptions = ['主角','配角','反派','路人']
const arcOptions = ['成长','堕落','救赎','顿悟','平淡','']

// 角色字段定义（显示用）
const displayFields = [
  { key:'identity', label:'身份' },
  { key:'age', label:'年龄' },
  { key:'gender', label:'性别' },
  { key:'occupation', label:'职业' },
  { key:'appearance', label:'外貌' },
  { key:'personality', label:'性格' },
  { key:'background', label:'背景' },
  { key:'ability', label:'能力' },
  { key:'story_goal', label:'目标' },
  { key:'motivation', label:'动机' },
  { key:'weakness', label:'弱点' },
  { key:'growth_experience', label:'成长经历' },
  { key:'character_change', label:'人物变化' },
  { key:'speech_style', label:'说话风格' },
  { key:'mental_state', label:'当前心理' },
]

async function onGenerate() {
  generating.value = true
  try { await api.generateCharacter({ role_type: genRole.value, extra: genExtra.value }); await refresh(); showGen.value=false; msg.success('角色生成完成') }
  catch (e:any) { msg.error('生成失败：'+formatError(e)) }
  finally { generating.value = false }
}
async function onBatch() {
  batchLoading.value = true
  try {
    const { task_id } = await api.batchGenerateCharactersAsync({ count: batchCount.value, requirements: batchReq.value })
    const { trackTask } = useBackgroundTasks()
    trackTask(task_id, 'characters', `批量生成${batchCount.value}个角色`)
    showBatch.value = false
    msg.success('批量生成任务已提交，可在右下角查看进度')
    setTimeout(() => refresh(), 5000)
  }
  catch (e:any) { msg.error('批量生成失败：'+formatError(e)) }
  finally { batchLoading.value = false }
}
function openEdit(c:any) {
  editing.value = c
  Object.keys(editForm).forEach(k => { (editForm as any)[k] = c[k] ?? (editForm as any)[k] })
}
async function onSave() {
  try { await api.updateCharacter(editing.value.id, { ...editForm }); await refresh(); editing.value=null; msg.success('已保存') }
  catch (e:any) { msg.error('保存失败：'+formatError(e)) }
}
async function onDelete(id:number) {
  if (!await msg.confirm('确认删除？')) return
  try { await api.deleteCharacter(id); await refresh(); msg.success('已删除') }
  catch (e:any) { msg.error('删除失败：'+formatError(e)) }
}
const roleColor: Record<string,string> = { '主角':'error', '反派':'warning', '配角':'processing', '路人':'default' }
</script>

<template>
  <div class="char-page">
    <div class="page-actions">
      <a-button @click="showBatch=true">批量生成</a-button>
      <a-button type="primary" @click="showGen=true">AI 生成角色</a-button>
    </div>

    <div v-if="characters && characters.length" class="char-grid">
      <a-card v-for="c in characters" :key="c.id" size="small" hoverable>
        <template #title>
          <div class="char-card-title">
            <span class="char-avatar">{{ (c.name||'?').charAt(0) }}</span>
            <span class="char-name">{{ c.name }}</span>
            <a-tag :color="roleColor[c.role]||'default'" size="small">{{ c.role }}</a-tag>
            <a-tag v-if="c.status && c.status!=='alive'" size="small">{{ c.status }}</a-tag>
            <div style="margin-left:auto">
              <a-button type="link" size="small" @click="openEdit(c)">编辑</a-button>
              <a-button type="link" danger size="small" @click="onDelete(c.id)">删除</a-button>
            </div>
          </div>
        </template>
        <!-- 内容平铺（描述列表） -->
        <div class="char-desc">
          <div v-for="f in displayFields" :key="f.key" v-show="c[f.key]" class="desc-row">
            <span class="desc-label">{{ f.label }}</span>
            <span class="desc-value">{{ c[f.key] }}</span>
          </div>
          <!-- 主职业阶段（#19） -->
          <div v-if="c.main_career_id || (c.sub_careers && c.sub_careers.length)" class="desc-row career-row">
            <span class="desc-label">修炼</span>
            <span class="desc-value">
              <a-tag v-if="c.main_career_id" color="gold" size="small">
                {{ careerNameById(c.main_career_id) }} Lv.{{ c.main_career_stage || 1 }}
              </a-tag>
              <a-tag v-for="sc in (c.sub_careers || [])" :key="sc.career_id" color="cyan" size="small">
                {{ sc.name }} Lv.{{ sc.stage || 1 }}
              </a-tag>
            </span>
          </div>
          <!-- 所属组织 -->
          <div v-if="c.organization_id && orgNameById(c.organization_id)" class="desc-row">
            <span class="desc-label">组织</span>
            <span class="desc-value"><a-tag color="blue" size="small">{{ orgNameById(c.organization_id) }}</a-tag></span>
          </div>
          <div v-if="!displayFields.some(f=>c[f.key]) && !c.main_career_id" class="desc-empty">暂无详细信息，点击编辑补充</div>
        </div>
      </a-card>
    </div>
    <a-empty v-else description="暂无角色，点击 AI 生成" />

    <!-- AI 生成 -->
    <a-modal v-model:open="showGen" title="AI 生成角色" width="420px">
      <a-form layout="vertical">
        <a-form-item label="角色定位"><a-select v-model:value="genRole"><a-select-option v-for="r in roleOptions" :key="r" :label="r" :value="r" /></a-select></a-form-item>
        <a-form-item label="补充要求"><a-textarea v-model:value="genExtra" :rows="3" /></a-form-item>
      </a-form>
      <template #footer><a-button @click="showGen=false">取消</a-button><a-button type="primary" :loading="generating" @click="onGenerate">{{ generating?'生成中…':'生成' }}</a-button></template>
    </a-modal>
    <!-- 批量 -->
    <a-modal v-model:open="showBatch" title="批量生成角色" width="480px">
      <a-form layout="vertical">
        <a-form-item label="数量"><a-input-number v-model:value="batchCount" :min="2" :max="10" /></a-form-item>
        <a-form-item label="需求"><a-textarea v-model:value="batchReq" :rows="3" /></a-form-item>
      </a-form>
      <template #footer><a-button @click="showBatch=false">取消</a-button><a-button type="primary" :loading="batchLoading" @click="onBatch">{{ batchLoading?'生成中…':'生成' }}</a-button></template>
    </a-modal>
    <!-- 编辑（弹窗，非抽屉）-->
    <a-modal :open="!!editing" @update:open="(v:any)=>{if(!v)editing=null}" title="编辑角色档案" width="680px" v-if="editing" :footer="null">
      <a-form layout="vertical">
        <a-divider orientation="left" plain>基本信息</a-divider>
        <a-row :gutter="12">
          <a-col :span="8"><a-form-item label="姓名"><a-input v-model:value="editForm.name" /></a-form-item></a-col>
          <a-col :span="8"><a-form-item label="定位"><a-select v-model:value="editForm.role"><a-select-option v-for="r in roleOptions" :key="r" :label="r" :value="r" /></a-select></a-form-item></a-col>
          <a-col :span="8"><a-form-item label="状态"><a-select v-model:value="editForm.status"><a-select-option label="存活" value="alive" /><a-select-option label="死亡" value="dead" /><a-select-option label="失踪" value="missing" /></a-select></a-form-item></a-col>
        </a-row>
        <a-row :gutter="12">
          <a-col :span="8"><a-form-item label="所属组织">
            <a-select v-model:value="editForm.organization_id" allow-clear placeholder="选择组织">
              <a-select-option :value="null">无</a-select-option>
              <a-select-option v-for="o in (organizations || [])" :key="o.id" :value="o.id">{{ o.name }}</a-select-option>
            </a-select>
          </a-form-item></a-col>
          <a-col :span="8"><a-form-item label="性别"><a-input v-model:value="editForm.gender" /></a-form-item></a-col>
          <a-col :span="8"><a-form-item label="年龄"><a-input v-model:value="editForm.age" /></a-form-item></a-col>
        </a-row>
        <a-row :gutter="12">
          <a-col :span="8"><a-form-item label="职业"><a-auto-complete v-model:value="editForm.occupation" :options="occupationOptions.map(o=>({value:o}))" :filter-option="(input:string, option:any)=>option.value.toLowerCase().includes(input.toLowerCase())" allow-clear :placeholder="occupationOptions.length?'选择或输入职业':'可直接输入'" /></a-form-item></a-col>
        </a-row>
        <a-form-item label="身份"><a-input v-model:value="editForm.identity" /></a-form-item>
        <a-divider orientation="left" plain>外貌与性格</a-divider>
        <a-form-item label="外貌"><a-textarea v-model:value="editForm.appearance" :rows="2" /></a-form-item>
        <a-form-item label="性格"><a-textarea v-model:value="editForm.personality" :rows="2" /></a-form-item>
        <a-divider orientation="left" plain>背景与成长</a-divider>
        <a-form-item label="背景"><a-textarea v-model:value="editForm.background" :rows="2" /></a-form-item>
        <a-form-item label="成长经历"><a-textarea v-model:value="editForm.growth_experience" :rows="2" /></a-form-item>
        <a-form-item label="能力"><a-textarea v-model:value="editForm.ability" :rows="2" /></a-form-item>
        <a-divider orientation="left" plain>动机与目标</a-divider>
        <a-form-item label="故事目标"><a-textarea v-model:value="editForm.story_goal" :rows="2" /></a-form-item>
        <a-form-item label="内在动机"><a-textarea v-model:value="editForm.motivation" :rows="2" /></a-form-item>
        <a-form-item label="弱点"><a-textarea v-model:value="editForm.weakness" :rows="2" /></a-form-item>
        <a-divider orientation="left" plain>人物变化</a-divider>
        <a-row :gutter="12">
          <a-col :span="12"><a-form-item label="变化类型"><a-select v-model:value="editForm.arc_type" allowClear><a-select-option v-for="a in arcOptions" :key="a" :label="a||'未设定'" :value="a" /></a-select></a-form-item></a-col>
          <a-col :span="12"><a-form-item label="当前心理"><a-input v-model:value="editForm.mental_state" /></a-form-item></a-col>
        </a-row>
        <a-form-item label="人物变化轨迹"><a-textarea v-model:value="editForm.character_change" :rows="2" /></a-form-item>
        <a-form-item label="说话风格"><a-input v-model:value="editForm.speech_style" /></a-form-item>
      </a-form>
      <div style="text-align:right;margin-top:12px;">
        <a-button @click="editing=null" style="margin-right:8px">取消</a-button>
        <a-button type="primary" @click="onSave">保存</a-button>
      </div>
    </a-modal>
  </div>
</template>

<style scoped>
.char-page { display:flex; flex-direction:column; gap:16px; }
.page-actions { display:flex; gap:8px; }
.char-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(380px,1fr)); gap:14px; }
.char-card-title { display:flex; align-items:center; gap:8px; }
.char-avatar { width:32px; height:32px; border-radius:50%; background:#4D8088; color:#fff; display:flex; align-items:center; justify-content:center; font-size:14px; font-weight:600; flex-shrink:0; }
.char-name { font-size:15px; font-weight:600; }
.char-desc { }
.desc-row { display:flex; gap:8px; padding:4px 0; border-bottom:1px solid #F8F6F1; font-size:13px; line-height:1.6; }
.desc-row:last-child { border-bottom:none; }
.desc-label { color:#8C8C8C; min-width:60px; flex-shrink:0; }
.desc-value { color:#2B2B2B; white-space:pre-wrap; }
.desc-empty { color:#bbb; font-size:13px; text-align:center; padding:12px; }
</style>
