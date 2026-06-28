<script setup lang="ts">
// 角色设定：对标参考站 — 卡片网格，每个角色内容平铺（描述列表风格）
import { API } from '~/composables/api'
import { useProject } from '~/composables/useProject'
import type { Career, Character } from '~/composables/api/types'

useHead({ title: '角色设定 — 墨语' })
const { currentProjectId, projectUrl } = useProject()
if (!currentProjectId.value) await navigateTo('/books')
const msg = useMessage()
const { onTaskCompleted } = useBackgroundTasks()

// 当角色生成任务完成时自动刷新列表
onTaskCompleted('characters', () => {
  refreshChars()
})
onTaskCompleted('init', () => {
  // 项目初始化完成后刷新（角色可能在初始化管线中生成）
  setTimeout(() => refreshChars(), 2000)
})
const { data: characters, refresh: refreshChars } = await useFetch<Character[]>(() => `/projects/${currentProjectId.value}/characters`)
// 加载职业体系，供「职业」字段下拉使用
const { data: careers, refresh: refreshCareers } = await useFetch<Career[]>(() => `/projects/${currentProjectId.value}/careers`)
// 加载组织列表，供「所属组织」字段下拉使用
const { data: organizations } = await API.organization.list()
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
// 主职业可选列表（career_type === "main"）
const mainCareers = computed(() => (careers.value || []).filter((c: any) => c.career_type === 'main'))
// 副职业可选列表（career_type === "sub"）
const subCareers = computed(() => (careers.value || []).filter((c: any) => c.career_type === 'sub'))
// 获取职业的阶段列表 [{name, level, ...}]
const careerStages = (careerId: number | null) => {
  if (!careerId) return []
  const c = (careers.value || []).find((x: any) => x.id === careerId)
  return (c?.stages || []).sort((a: any, b: any) => (a.level || 0) - (b.level || 0))
}
// 副职业可选列表：只显示 career_type=sub，排除已在其他行选中的
const availableSubCareers = (currentIdx: number) => {
  const excludeIds = new Set<number | null>()
  editForm.sub_careers.forEach((sc, i) => {
    if (i !== currentIdx && sc.career_id) excludeIds.add(sc.career_id)
  })
  return subCareers.value.filter(cr => !excludeIds.has(cr.id))
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
const genCount = ref(1)
const genOrgId = ref<number | null>(null)
const generating = ref(false)
const showBatch = ref(false)
const batchRoles = ref<Array<{ role: string; count: number }>>([
  { role: '主角', count: 1 },
  { role: '配角', count: 3 },
  { role: '反派', count: 1 },
])
const batchReq = ref('')
const batchLoading = ref(false)

const editing = ref<any>(null)
const editForm = reactive({
  name:'', role:'配角', gender:'', age:'', identity:'',
  appearance:'', personality:'', background:'', growth_experience:'', ability:'',
  story_goal:'', motivation:'', weakness:'', arc_type:'', character_change:'', speech_style:'',
  status:'alive', mental_state:'', organization_id: null as number | null,
  main_career_id: null as number | null, main_career_stage_desc: '',
  sub_careers: [] as Array<{ career_id: number | null; name: string; stage_desc: string }>,
})
const roleOptions = ['主角','配角','反派','路人']
const arcOptions = ['成长','堕落','救赎','顿悟','平淡','']
const statusLabels: Record<string, string> = { alive: '存活', dead: '死亡', missing: '失踪', retired: '退隐' }

// ===== 角色变化日志 =====
const changeLogs = ref<any[]>([])
const showChangeLogForm = ref(false)
const newLog = reactive({ chapter_number: null as number | null, summary: '', changed_fields: {} as Record<string, any> })
const trackableFields = [
  { key: 'status', label: '状态' },
  { key: 'personality', label: '性格' },
  { key: 'mental_state', label: '当前心理' },
  { key: 'appearance', label: '外貌' },
  { key: 'ability', label: '能力' },
  { key: 'arc_type', label: '变化类型' },
  { key: 'speech_style', label: '说话风格' },
  { key: 'main_career_stage_desc', label: '境界' },
]
async function loadChangeLogs(charId: number) {
  const res = await API.character.getChangeLogs(charId)
  const d = (res as any)?.data
  changeLogs.value = (d?.value ?? d ?? []) as any[]
}
function openAddLog() {
  newLog.chapter_number = null
  newLog.summary = ''
  newLog.changed_fields = {}
  showChangeLogForm.value = true
}
async function onAddLog() {
  const charId = logCharacter.value?.id
  if (!charId || !newLog.chapter_number) { msg.warning('请输入章节号'); return }
  try {
    await API.character.createChangeLog(charId, {
      chapter_number: newLog.chapter_number,
      summary: newLog.summary,
      changed_fields: newLog.changed_fields,
    })
    showChangeLogForm.value = false
    await loadChangeLogs(charId)
    msg.success('已添加变化记录')
  } catch (e: any) { msg.error('添加失败：' + formatError(e)) }
}
async function onDeleteLog(logId: number) {
  const charId = logCharacter.value?.id
  if (!charId) return
  if (!await msg.confirm('确认删除此变化记录？')) return
  try {
    await API.character.deleteChangeLog(charId, logId)
    await loadChangeLogs(charId)
    msg.success('已删除')
  } catch (e: any) { msg.error('删除失败：' + formatError(e)) }
}
function toggleChangedField(key: string) {
  if (newLog.changed_fields[key]) {
    delete newLog.changed_fields[key]
  } else {
    newLog.changed_fields[key] = (editForm as any)[key] ?? ''
  }
}

async function loadCharOrgs(charId: number) {
  const res = await API.character.getOrganizations(charId)
  const d = (res as any)?.data
  charOrgs.value = (d?.value ?? d ?? []) as any[]
}

// ===== 独立人物日志弹窗 =====
const showLogModal = ref(false)
const logCharacter = ref<any>(null)
const charOrgs = ref<any[]>([])  // 角色所属的所有组织

function openChangeLog(c: any) {
  logCharacter.value = c
  showLogModal.value = true
  loadChangeLogs(c.id)
}

const displayFields = [
  { key:'identity', label:'身份' },
  { key:'age', label:'年龄' },
  { key:'gender', label:'性别' },
  { key:'appearance', label:'外貌' },
  { key:'personality', label:'性格' },
  { key:'background', label:'背景' },
  { key:'ability', label:'能力' },
  { key:'story_goal', label:'目标' },
  { key:'motivation', label:'动机' },
  { key:'weakness', label:'弱点' },
  { key:'growth_experience', label:'成长经历' },
  { key:'arc_type', label:'变化类型' },
  { key:'character_change', label:'人物变化轨迹' },
  { key:'speech_style', label:'说话风格' },
  { key:'mental_state', label:'当前心理' },
]

async function onGenerate() {
  // 组织补充要求（让 AI 知道有哪些组织可选）
  const orgName = genOrgId.value ? (organizations.value || []).find((o:any)=>o.id===genOrgId.value)?.name : ''
  const orgHint = orgName ? `该角色应属于「${orgName}」组织。` : (genOrgId.value === null ? '' : '')
  const extra = (genExtra.value ? genExtra.value + ' ' : '') + orgHint
  generating.value = true
  try {
    if (genCount.value > 1) {
      // 数量>1 走批量生成
      const { task_id } = await API.character.batchGenerate({ count: genCount.value, requirements: `${genRole.value}。${extra}` })
      const { trackTask } = useBackgroundTasks()
      trackTask({ id: task_id, task_type: 'characters', title: `批量生成${genCount.value}个角色` })
	      showGen.value = false
	      msg.success('批量生成任务已提交，可在右下角查看进度')
	    } else {
	      // 单个生成也走异步任务，避免前台阻塞
	      const { task_id } = await API.character.batchGenerate({ count: 1, requirements: `${genRole.value}。${extra}` })
	      const { trackTask } = useBackgroundTasks()
	      trackTask({ id: task_id, task_type: 'characters', title: `生成${genRole.value}角色` })
	      showGen.value = false
	      msg.success('生成任务已提交，可在右下角查看进度')
	    }
  } catch (e:any) { msg.error('生成失败：'+formatError(e)) }
  finally { generating.value = false }
}
async function onBatch() {
  batchLoading.value = true
  try {
    const roleList = batchRoles.value.filter(r => r.count > 0)
    const totalCount = roleList.reduce((sum, r) => sum + r.count, 0)
    if (totalCount === 0) { msg.warning('请至少设置一种角色数量'); return }
    const roleDesc = roleList.map(r => `${r.role}${r.count}个`).join('、')
    const reqText = `请生成${roleDesc}。${batchReq.value}`
    const { task_id } = await API.character.batchGenerate({ count: totalCount, requirements: reqText })
    const { trackTask } = useBackgroundTasks()
    trackTask({ id: task_id, task_type: 'characters', title: `批量生成${totalCount}个角色（${roleDesc}）` })
	    showBatch.value = false
	    msg.success('批量生成任务已提交，可在右下角查看进度')
  }
  catch (e:any) { msg.error('批量生成失败：'+formatError(e)) }
  finally { batchLoading.value = false }
}
function openEdit(c:any) {
  editing.value = c
  Object.keys(editForm).forEach(k => {
    if (k === 'main_career_stage_desc') {
      (editForm as any)[k] = c.main_career_stage_desc || c.main_career_stage || ''
    } else if (k === 'sub_careers') {
      (editForm as any)[k] = (c.sub_careers || []).map((sc: any) => ({
        career_id: sc.career_id || null,
        name: sc.name || '',
        stage_desc: sc.stage_desc || sc.stage || '',
      }))
    } else {
      (editForm as any)[k] = c[k] ?? (editForm as any)[k]
    }
  })
  loadChangeLogs(c.id)
  loadCharOrgs(c.id)
}
async function onSave() {
  try {
    // 副职业：根据 career_id 补全 name
    const subs = (editForm.sub_careers || [])
      .filter(sc => sc.career_id)
      .map(sc => ({
        career_id: sc.career_id,
        name: careerNameById(sc.career_id!),
        stage_desc: sc.stage_desc || '',
      }))
    const payload = { ...editForm, sub_careers: subs }
    await API.character.update(editing.value.id, payload)
    await refreshChars()
    editing.value = null
    msg.success('已保存')
  } catch (e: any) { msg.error('保存失败：' + formatError(e)) }
}

async function onDelete(id:number) {
  if (!await msg.confirm('确认删除？')) return
  try { await API.character.delete(id); await refreshChars(); msg.success('已删除') }
  catch (e:any) { msg.error('删除失败：'+formatError(e)) }
}
const roleColor: Record<string,string> = { '主角':'error', '反派':'warning', '配角':'processing', '路人':'default' }

// 展开/折叠
const expandedChars = ref<Set<number>>(new Set())
function toggleExpand(id: number) {
  if (expandedChars.value.has(id)) expandedChars.value.delete(id)
  else expandedChars.value.add(id)
}

// 人际关系（从关系表获取）
const charRelations = ref<Record<number, string[]>>({})
async function loadAllRelations() {
  try {
    const res = await API.relation.list()
    const d = (res as any)?.data
    const rels = (d?.value ?? d ?? []) as any[]
    const map: Record<number, string[]> = {}
    for (const r of rels) {
      const other = r.from_character_id === r.to_character_id ? null : null
      if (r.from_character_id && r.to_character_id && r.from_character_id !== r.to_character_id) {
        const nameA = r.from_name || ''
        const nameB = r.to_name || ''
        if (nameA && nameB) {
          if (!map[r.from_character_id]) map[r.from_character_id] = []
          if (!map[r.to_character_id]) map[r.to_character_id] = []
          map[r.from_character_id].push(`${nameB}：${r.relation_type}`)
          map[r.to_character_id].push(`${nameA}：${r.relation_type}`)
        }
      }
    }
    charRelations.value = map
  } catch { /* ignore */ }
}
loadAllRelations()
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
            <a-tag v-if="c.status && c.status!=='alive'" size="small" :color="c.status==='dead'?'red':c.status==='missing'?'orange':'default'">{{ statusLabels[c.status] || c.status }}</a-tag>
            <div style="margin-left:auto">
              <a-button type="link" size="small" @click="openChangeLog(c)">📋 日志</a-button>
              <a-button type="link" size="small" @click="openEdit(c)">编辑</a-button>
              <a-button type="link" danger size="small" @click="onDelete(c.id)">删除</a-button>
            </div>
          </div>
        </template>
        <!-- 内容 -->
        <div class="char-desc">
          <!-- 基本信息（始终显示） -->
          <div class="desc-row" v-if="c.identity"><span class="desc-label">身份</span><span class="desc-value">{{ c.identity }}</span></div>
          <div class="desc-row" v-if="c.age"><span class="desc-label">年龄</span><span class="desc-value">{{ c.age }}</span></div>
          <div class="desc-row" v-if="c.gender"><span class="desc-label">性别</span><span class="desc-value">{{ c.gender }}</span></div>
          <!-- 主修 -->
          <div v-if="c.main_career_id" class="desc-row"><span class="desc-label">主修</span><span class="desc-value"><a-tag color="gold" size="small">{{ careerNameById(c.main_career_id) }}<span v-if="c.main_career_stage_desc"> · {{ c.main_career_stage_desc }}</span></a-tag></span></div>
          <!-- 副修 -->
          <div v-if="(c.sub_careers || []).length" class="desc-row"><span class="desc-label">副修</span><span class="desc-value"><a-tag v-for="(sc, i) in (c.sub_careers || [])" :key="i" color="cyan" size="small" style="margin-right:4px">{{ sc.name || careerNameById(sc.career_id) }}<span v-if="sc.stage_desc"> · {{ sc.stage_desc }}</span></a-tag></span></div>
          <!-- 组织 -->
          <div v-if="c.organization_id" class="desc-row"><span class="desc-label">组织</span><span class="desc-value"><a-tag color="blue" size="small">{{ orgNameById(c.organization_id) }}</a-tag></span></div>

          <!-- 展开内容 -->
          <template v-if="expandedChars.has(c.id)">
            <div v-for="f in displayFields" :key="f.key" v-show="c[f.key] && !['identity','age','gender'].includes(f.key)" class="desc-row">
              <span class="desc-label">{{ f.label }}</span>
              <span class="desc-value">{{ c[f.key] }}</span>
            </div>
            <!-- 人际关系 -->
            <div v-if="charRelations[c.id]?.length" class="desc-row"><span class="desc-label">关系</span><span class="desc-value" style="font-size:12px;line-height:1.8;">{{ charRelations[c.id].join('；') }}</span></div>
          </template>
          
          <div v-if="!c.identity && !c.age && !c.gender && !c.main_career_id && !(c.sub_careers||[]).length" class="desc-empty">暂无详细信息，点击编辑补充</div>
        </div>
        <div style="text-align:center;margin-top:4px;">
          <a-button type="link" size="small" @click="toggleExpand(c.id)">{{ expandedChars.has(c.id) ? '收起 ▲' : '展开 ▼' }}</a-button>
        </div>
      </a-card>
    </div>
    <a-empty v-else description="暂无角色，点击 AI 生成" />

    <!-- AI 生成 -->
    <a-modal v-model:open="showGen" title="AI 生成角色" width="460px">
      <a-form layout="vertical">
        <a-row :gutter="12">
          <a-col :span="12"><a-form-item label="角色定位"><a-select v-model:value="genRole"><a-select-option v-for="r in roleOptions" :key="r" :label="r" :value="r" /></a-select></a-form-item></a-col>
          <a-col :span="12"><a-form-item label="生成数量"><a-input-number v-model:value="genCount" :min="1" :max="10" style="width:100%" /></a-form-item></a-col>
        </a-row>
        <a-form-item label="所属组织"><a-select v-model:value="genOrgId" allow-clear placeholder="选择组织（AI 会据此分配）">
          <a-select-option :value="null">不限</a-select-option>
          <a-select-option v-for="o in (organizations || [])" :key="o.id" :value="o.id">{{ o.name }}</a-select-option>
        </a-select></a-form-item>
        <a-form-item label="补充要求"><a-textarea v-model:value="genExtra" :rows="3" placeholder="可选：对角色的额外要求" /></a-form-item>
      </a-form>
      <template #footer><a-button @click="showGen=false">取消</a-button><a-button type="primary" :loading="generating" @click="onGenerate">{{ generating?'生成中…':`生成 ${genCount} 个` }}</a-button></template>
    </a-modal>
    <!-- 批量 -->
    <a-modal v-model:open="showBatch" title="批量生成角色" width="500px">
      <a-form layout="vertical">
        <a-form-item label="角色类型与数量">
          <div v-for="(br, idx) in batchRoles" :key="idx" style="display:flex;gap:8px;align-items:center;margin-bottom:6px;">
            <a-select v-model:value="br.role" style="width:100px" size="small">
              <a-select-option v-for="r in roleOptions" :key="r" :value="r">{{ r }}</a-select-option>
            </a-select>
            <a-input-number v-model:value="br.count" :min="0" :max="10" size="small" style="width:80px" />
            <span style="font-size:12px;color:#999;">个</span>
            <a-button v-if="batchRoles.length > 1" size="small" danger type="link" @click="batchRoles.splice(idx, 1)">✕</a-button>
          </div>
          <a-button size="small" type="dashed" @click="batchRoles.push({ role: '配角', count: 1 })">+ 添加角色类型</a-button>
        </a-form-item>
        <a-form-item label="补充要求"><a-textarea v-model:value="batchReq" :rows="3" placeholder="可选：对角色生成的额外要求" /></a-form-item>
      </a-form>
      <template #footer>
        <a-button @click="showBatch=false">取消</a-button>
        <a-button type="primary" :loading="batchLoading" @click="onBatch">
          {{ batchLoading ? '生成中…' : `生成 ${batchRoles.reduce((s,r)=>s+r.count,0)} 个` }}
        </a-button>
      </template>
    </a-modal>
    <!-- 编辑（弹窗，非抽屉）-->
    <a-modal :open="!!editing" @update:open="(v:any)=>{if(!v)editing=null}" title="编辑角色档案" width="680px" v-if="editing" :footer="null">
      <div style="font-size:11px;color:#999;margin-bottom:8px;"><span style="color:#e91e63;font-weight:600;">*</span> 标记的字段会被章节分析自动更新</div>
      <a-form layout="vertical">
        <a-divider orientation="left" plain>基本信息</a-divider>
        <a-row :gutter="12">
          <a-col :span="8"><a-form-item label="姓名"><a-input v-model:value="editForm.name" /></a-form-item></a-col>
          <a-col :span="8"><a-form-item label="定位"><a-select v-model:value="editForm.role"><a-select-option v-for="r in roleOptions" :key="r" :label="r" :value="r" /></a-select></a-form-item></a-col>
          <a-col :span="8"><a-form-item label="状态" class="dynamic-label"><a-select v-model:value="editForm.status"><a-select-option value="alive">存活</a-select-option><a-select-option value="dead">死亡</a-select-option><a-select-option value="missing">失踪</a-select-option><a-select-option value="retired">退隐</a-select-option></a-select></a-form-item></a-col>
        </a-row>
        <a-row :gutter="12">
          <a-col :span="8"><a-form-item label="组织">
            <div v-if="charOrgs.length" style="display:flex;flex-wrap:wrap;gap:4px;">
              <a-tag v-for="o in charOrgs" :key="o.id" color="blue" size="small">{{ o.name }}<span v-if="o.position"> · {{ o.position }}</span></a-tag>
            </div>
            <span v-else style="color:#ccc;font-size:12px;">暂无</span>
            <div style="font-size:11px;color:#8C8C8C;margin-top:2px;">💡 在「<NuxtLink :to="projectUrl('/organizations')" style="color:#4D8088;">组织与势力</NuxtLink>」页面管理</div>
          </a-form-item></a-col>
          <a-col :span="8"><a-form-item label="性别"><a-input v-model:value="editForm.gender" /></a-form-item></a-col>
          <a-col :span="8"><a-form-item label="年龄"><a-input v-model:value="editForm.age" /></a-form-item></a-col>
        </a-row>
        <!-- 主职业：修炼体系 + 境界 -->
        <a-row :gutter="12">
          <a-col :span="14"><a-form-item label="主职业（修炼体系）">
            <a-select v-model:value="editForm.main_career_id" allow-clear placeholder="选择修炼体系">
              <a-select-option :value="null">未设定</a-select-option>
              <a-select-option v-for="cr in mainCareers" :key="cr.id" :value="cr.id">{{ cr.name }}</a-select-option>
            </a-select>
          </a-form-item></a-col>
          <a-col :span="10"><a-form-item label="境界" class="dynamic-label">
            <a-select
              v-model:value="editForm.main_career_stage_desc"
              allow-clear
              placeholder="选择境界"
              :disabled="!editForm.main_career_id"
            >
              <a-select-option
                v-for="st in careerStages(editForm.main_career_id)"
                :key="st.level"
                :value="st.name"
              >{{ st.name }}{{ st.level != null ? ' (Lv.' + st.level + ')' : '' }}</a-select-option>
            </a-select>
          </a-form-item></a-col>
        </a-row>

        <!-- 副职业：多条修炼体系+境界（动态增删） -->
        <a-form-item label="副职业">
          <div v-for="(sc, idx) in editForm.sub_careers" :key="idx">
            <a-row :gutter="12" style="margin-bottom:6px;align-items:center;">
              <a-col :span="12">
                <a-select v-model:value="sc.career_id" allow-clear placeholder="修炼体系">
                  <a-select-option :value="null">未设定</a-select-option>
                  <a-select-option v-for="cr in availableSubCareers(idx)" :key="cr.id" :value="cr.id">{{ cr.name }}</a-select-option>
                </a-select>
              </a-col>
              <a-col :span="10">
                <a-select v-model:value="sc.stage_desc" allow-clear placeholder="境界" :disabled="!sc.career_id">
                  <a-select-option v-for="st in careerStages(sc.career_id)" :key="st.level" :value="st.name">{{ st.name }}</a-select-option>
                </a-select>
              </a-col>
              <a-col :span="2" style="text-align:right;">
                <a-button size="small" danger type="link" @click="editForm.sub_careers.splice(idx, 1)">✕</a-button>
              </a-col>
            </a-row>
          </div>
          <a-button size="small" type="dashed" @click="editForm.sub_careers.push({ career_id: null, name: '', stage_desc: '' })">
            + 添加副职业
          </a-button>
        </a-form-item>
        <a-form-item label="身份"><a-input v-model:value="editForm.identity" /></a-form-item>
        <a-divider orientation="left" plain>外貌与性格</a-divider>
        <a-form-item label="外貌"><a-textarea v-model:value="editForm.appearance" :rows="2" /></a-form-item>
        <a-form-item label="性格" class="dynamic-label"><a-textarea v-model:value="editForm.personality" :rows="2" /></a-form-item>
        <a-divider orientation="left" plain>背景与成长</a-divider>
        <a-form-item label="背景"><a-textarea v-model:value="editForm.background" :rows="2" /></a-form-item>
        <a-form-item label="成长经历"><a-textarea v-model:value="editForm.growth_experience" :rows="2" /></a-form-item>
        <a-form-item label="能力" class="dynamic-label"><a-textarea v-model:value="editForm.ability" :rows="2" /></a-form-item>
        <a-divider orientation="left" plain>动机与目标</a-divider>
        <a-form-item label="故事目标"><a-textarea v-model:value="editForm.story_goal" :rows="2" /></a-form-item>
        <a-form-item label="内在动机"><a-textarea v-model:value="editForm.motivation" :rows="2" /></a-form-item>
        <a-form-item label="弱点"><a-textarea v-model:value="editForm.weakness" :rows="2" /></a-form-item>
        <a-divider orientation="left" plain>人物变化 <span style="font-size:11px;color:#999;font-weight:normal;">（变化类型/轨迹随章节自动累积更新）</span></a-divider>
        <a-row :gutter="12">
          <a-col :span="12"><a-form-item label="变化类型" class="dynamic-label"><a-select v-model:value="editForm.arc_type" allowClear><a-select-option v-for="a in arcOptions" :key="a" :label="a||'未设定'" :value="a" /></a-select></a-form-item></a-col>
          <a-col :span="12"><a-form-item label="当前心理" class="dynamic-label"><a-input v-model:value="editForm.mental_state" /></a-form-item></a-col>
        </a-row>
        <a-form-item label="人物变化轨迹" class="dynamic-label"><a-textarea v-model:value="editForm.character_change" :rows="3" placeholder="随章节自动累积（第N章：xxx），也可手动补充" /></a-form-item>
        <a-form-item label="说话风格"><a-input v-model:value="editForm.speech_style" /></a-form-item>
      </a-form>
      <div style="text-align:right;margin-top:12px;">
        <a-button @click="editing=null" style="margin-right:8px">取消</a-button>
        <a-button type="primary" @click="onSave">保存</a-button>
      </div>
    </a-modal>

    <!-- 人物日志独立弹窗 -->
    <a-modal v-model:open="showLogModal" :title="`📋 ${logCharacter?.name || ''} 变化日志`" width="640px">
      <div v-if="changeLogs.length" class="change-log-list">
        <div v-for="log in changeLogs" :key="log.id" class="change-log-item">
          <span class="log-chapter">第{{ log.chapter_number }}章</span>
          <span class="log-fields">
            <a-tag v-for="(v, k) in log.changed_fields" :key="k" size="small" color="blue">{{ trackableFields.find(f=>f.key===k)?.label || k }}: {{ v }}</a-tag>
          </span>
          <span v-if="log.summary" class="log-summary">{{ log.summary }}</span>
          <a-button type="link" danger size="small" @click="onDeleteLog(log.id)" style="margin-left:auto">✕</a-button>
        </div>
      </div>
      <a-empty v-else description="暂无变化记录" />
      <div v-if="!showChangeLogForm" style="margin-top:12px;">
        <a-button size="small" @click="openAddLog">＋ 添加变化</a-button>
      </div>
      <div v-else class="change-log-form">
        <a-row :gutter="12">
          <a-col :span="6"><a-form-item label="章节号"><a-input-number v-model:value="newLog.chapter_number" :min="1" style="width:100%" /></a-form-item></a-col>
          <a-col :span="18"><a-form-item label="摘要"><a-input v-model:value="newLog.summary" placeholder="如：受伤后性格大变" /></a-form-item></a-col>
        </a-row>
        <a-form-item label="变更字段">
          <a-checkable-tag v-for="f in trackableFields" :key="f.key" :checked="!!newLog.changed_fields[f.key]" @change="toggleChangedField(f.key)" style="margin:2px 4px;">{{ f.label }}</a-checkable-tag>
        </a-form-item>
        <a-button size="small" type="primary" @click="onAddLog">确认添加</a-button>
        <a-button size="small" @click="showChangeLogForm = false" style="margin-left:8px">取消</a-button>
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
/* 动态字段标记 */
.dynamic-label :deep(.ant-form-item-label > label)::after {
  content: ' *';
  color: #e91e63;
  font-weight: bold;
  font-size: 14px;
}
/* 变化日志 */
.change-log-list { max-height: 200px; overflow-y: auto; margin-bottom: 8px; }
.change-log-item { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid #f5f5f5; font-size: 12px; }
.change-log-item:last-child { border-bottom: none; }
.log-chapter { font-weight: 600; color: #4D8088; min-width: 50px; }
.log-fields { display: flex; gap: 4px; flex-wrap: wrap; flex: 1; }
.log-summary { color: #888; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.change-log-form { background: #fafafa; border: 1px solid #f0f0f0; border-radius: 8px; padding: 12px; margin: 8px 0; }
</style>
