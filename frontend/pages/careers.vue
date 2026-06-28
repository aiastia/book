<script setup lang="ts">
// 职业体系：主/副职业分页 + 详细卡片（对标参考站）
import { useBookApi } from '~/composables/useBookApi'
import { useProject } from '~/composables/useProject'

useHead({ title: '职业体系 — 墨语' })
const { currentProjectId } = useProject()
if (!currentProjectId.value) await navigateTo('/books')
const api = useBookApi()
const msg = useMessage()
const { data: careers, refresh: refreshCareers } = await useFetch(() => `/projects/${currentProjectId.value}/careers`)
// 角色职业关联（#19，显示持有此职业的角色）
const { data: charCareers } = await api.getCharCareers()
// 角色名映射
const { data: characters, refresh: refreshChars } = await useFetch(() => `/projects/${currentProjectId.value}/characters`)
const charNameMap = computed(() => {
  const m: Record<number, string> = {}
  for (const c of (characters.value || [])) m[c.id] = c.name
  return m
})
const holdersByCareer = computed(() => {
  const m: Record<number, any[]> = {}
  for (const cc of (charCareers.value || [])) {
    if (!m[cc.career_id]) m[cc.career_id] = []
    m[cc.career_id].push({
      ...cc,
      character_name: cc.character_name || charNameMap.value[cc.character_id] || '',
    })
  }
  return m
})

const generating = ref(false)
const showAdd = ref(false)
const showGen = ref(false)
const newCareer = reactive({ name: '', career_type: 'main', category: '', description: '' })
const editing = ref<any>(null)
// 编辑表单（含 stages 进阶阶段 + abilities 能力，可增删改）
const editForm = reactive({
  name: '', career_type: 'main', category: '', description: '',
  stages: [] as any[],
  abilities: [] as any[],
})

// 追加生成
const genCount = ref(3)
const genType = ref<'all' | 'main' | 'sub'>('all')
const genReq = ref('')

// 阶段编辑辅助
function addStage() {
  editForm.stages.push({ name: '', description: '', requirement: '', ability: '' })
}
function removeStage(i: number) {
  editForm.stages.splice(i, 1)
}
function moveStage(i: number, dir: -1 | 1) {
  const j = i + dir
  if (j < 0 || j >= editForm.stages.length) return
  const tmp = editForm.stages[i]
  editForm.stages[i] = editForm.stages[j]
  editForm.stages[j] = tmp
}
// 能力编辑辅助
const newAbility = ref('')
function addAbility() {
  if (newAbility.value.trim()) {
    editForm.abilities.push({ name: newAbility.value.trim() })
    newAbility.value = ''
  }
}
function removeAbility(i: number) {
  editForm.abilities.splice(i, 1)
}

// 主/副职业切换
const activeType = ref<'all' | 'main' | 'sub'>('all')
const filteredCareers = computed(() => {
  const list = careers.value || []
  if (activeType.value === 'all') return list
  return list.filter((c: any) => (c.career_type || 'main') === activeType.value)
})
const countMain = computed(() => (careers.value || []).filter((c: any) => (c.career_type || 'main') === 'main').length)
const countSub = computed(() => (careers.value || []).filter((c: any) => c.career_type === 'sub').length)

// 统一解析阶段（兼容 string / object）
function stageName(s: any): string {
  if (typeof s === 'string') return s
  return s?.name || s?.stage_name || s?.level || JSON.stringify(s)
}
function stageDetail(s: any): string {
  if (typeof s === 'string') return ''
  const parts = [s?.requirement, s?.ability, s?.description].filter(Boolean)
  return parts.join(' · ')
}

async function onGenerate() {
  // 打开生成弹窗（支持追加模式）
  showGen.value = true
}
async function doGenerate() {
  generating.value = true
  try {
    const hasExisting = (careers.value || []).length > 0
    const r = await api.generateCareerSystem({
      append: hasExisting,  // 已有职业时追加，不覆盖
      count: genCount.value,
      career_type: genType.value === 'all' ? '' : genType.value,
      user_prompt: genReq.value,
    })
    await refresh()
    showGen.value = false
    msg.success(hasExisting ? `追加生成 ${r.count} 个职业` : `生成 ${r.count} 个职业`)
  } catch (e: any) { msg.error('生成失败：' + formatError(e)) }
  finally { generating.value = false }
}
async function onAdd() {
  if (!newCareer.name.trim()) return
  try { await api.createCareer({ ...newCareer, stages: [], abilities: [], attributes: {} }); showAdd.value = false; newCareer.name = ''; await refresh() }
  catch (e: any) { msg.error('添加失败：' + formatError(e)) }
}
function openEdit(c: any) {
  editing.value = c
  // 加载 stages/abilities（统一成数组对象格式）
  const rawStages = c.stages || []
  const stages = rawStages.map((s: any) => {
    if (typeof s === 'string') return { name: s, description: '', requirement: '', ability: '' }
    return { name: s.name || s.stage_name || '', description: s.description || '', requirement: s.requirement || '', ability: s.ability || '' }
  })
  const rawAbilities = c.abilities || []
  const abilities = rawAbilities.map((a: any) => {
    if (typeof a === 'string') return { name: a }
    return { name: a.name || a.ability || String(a), description: a.description || '' }
  })
  Object.assign(editForm, {
    name: c.name, career_type: c.career_type || 'main', category: c.category || '', description: c.description || '',
    stages, abilities,
  })
}
async function onSave() {
  try {
    // 把 stages 规整为后端期望的格式
    const cleanStages = editForm.stages.filter(s => s.name && s.name.trim()).map(s => ({
      name: s.name.trim(),
      description: s.description || '',
      requirement: s.requirement || '',
      ability: s.ability || '',
    }))
    const cleanAbilities = editForm.abilities.filter(a => a.name && a.name.trim()).map(a => ({
      name: a.name.trim(),
      description: a.description || '',
    }))
    await api.updateCareer(editing.value.id, {
      name: editForm.name,
      career_type: editForm.career_type,
      category: editForm.category,
      description: editForm.description,
      stages: cleanStages,
      abilities: cleanAbilities,
    })
    await refresh(); editing.value = null; msg.success('已保存')
  } catch (e: any) { msg.error('保存失败：' + formatError(e)) }
}
async function onDelete(id: number) {
  if (!await msg.confirm('确认删除？')) return
  try { await api.deleteCareer(id); await refresh(); msg.success('已删除') }
  catch (e: any) { msg.error('删除失败：' + formatError(e)) }
}

const typeLabel: Record<string, string> = { main: '主职业', sub: '副职业' }
const typeColor: Record<string, string> = { main: 'gold', sub: 'cyan' }
const categoryColor: Record<string, string> = {
  战斗: 'red', 辅助: 'blue', 生产: 'green', 特殊: 'purple',
}

// AI 自动分配角色职业（#19）
const autoAssigning = ref(false)
async function onAutoAssign() {
  if (!await msg.confirm('AI 将根据角色性格背景和职业体系，为未分配职业的角色推荐主职业。确认开始？')) return
  autoAssigning.value = true
  try {
    const r = await api.autoAssignCareers({ user_prompt: '' })
    await refresh()
    msg.success(`已为 ${r.count} 个角色分配主职业`)
  } catch (e: any) { msg.error('分配失败：' + formatError(e)) }
  finally { autoAssigning.value = false }
}
</script>

<template>
  <PageHeader title="职业体系">
    <template #actions>
      <a-button @click="showAdd = true">+ 添加职业</a-button>
      <a-button :loading="autoAssigning" @click="onAutoAssign">{{ autoAssigning ? '分配中…' : '🤖 AI 分配角色职业' }}</a-button>
      <a-button type="primary" :loading="generating" @click="onGenerate">{{ generating ? '生成中…' : ((careers||[]).length ? '➕ 追加生成' : 'AI 生成体系') }}</a-button>
    </template>
  </PageHeader>

  <div class="page-content">
    <!-- 主/副职业切换 -->
    <div class="type-tabs">
      <a-checkable-tag :checked="activeType === 'all'" @change="activeType = 'all'">
        全部 <span class="cnt">{{ (careers || []).length }}</span>
      </a-checkable-tag>
      <a-checkable-tag :checked="activeType === 'main'" @change="activeType = 'main'">
        ⚔️ 主职业 <span class="cnt">{{ countMain }}</span>
      </a-checkable-tag>
      <a-checkable-tag :checked="activeType === 'sub'" @change="activeType = 'sub'">
        🔧 副职业 <span class="cnt">{{ countSub }}</span>
      </a-checkable-tag>
    </div>

    <div v-if="filteredCareers.length" class="career-grid">
      <a-card v-for="c in filteredCareers" :key="c.id" hoverable>
        <!-- 标题栏 -->
        <div class="card-head">
          <div class="head-left">
            <span class="career-icon">{{ c.career_type === 'sub' ? '🔧' : '⚔️' }}</span>
            <span class="career-name">{{ c.name }}</span>
            <a-tag :color="typeColor[c.career_type] || 'default'" size="small">{{ typeLabel[c.career_type] || c.career_type }}</a-tag>
            <a-tag v-if="c.category" :color="categoryColor[c.category] || 'default'" size="small">{{ c.category }}</a-tag>
          </div>
          <div class="head-actions">
            <a-button type="link" size="small" @click="openEdit(c)">编辑</a-button>
            <a-button type="link" danger size="small" @click="onDelete(c.id)">删除</a-button>
          </div>
        </div>

        <!-- 描述 -->
        <div v-if="c.description" class="career-desc">{{ c.description }}</div>

        <!-- 进阶阶段时间线 -->
        <div v-if="c.stages && c.stages.length" class="career-section">
          <div class="section-title">📌 进阶阶段（{{ c.stages.length }}）</div>
          <div class="stage-timeline">
            <div v-for="(st, i) in c.stages" :key="i" class="stage-item">
              <div class="stage-index">{{ Number(i) + 1 }}</div>
              <div class="stage-body">
                <div class="stage-name">{{ stageName(st) }}</div>
                <div v-if="stageDetail(st)" class="stage-detail">{{ stageDetail(st) }}</div>
              </div>
              <div v-if="Number(i) < c.stages.length - 1" class="stage-arrow">→</div>
            </div>
          </div>
        </div>

        <!-- 能力列表 -->
        <div v-if="c.abilities && c.abilities.length" class="career-section">
          <div class="section-title">✨ 能力（{{ c.abilities.length }}）</div>
          <div class="ability-list">
            <div v-for="(ab, i) in c.abilities" :key="i" class="ability-item">
              <a-tag color="blue" size="small">{{ typeof ab === 'string' ? ab : (ab.name || ab) }}</a-tag>
            </div>
          </div>
        </div>

        <!-- 持有此职业的角色（#19） -->
        <div v-if="holdersByCareer[c.id] && holdersByCareer[c.id].length" class="career-section">
          <div class="section-title">👥 修炼者（{{ holdersByCareer[c.id].length }}）</div>
          <div class="holder-list">
            <span v-for="h in holdersByCareer[c.id]" :key="h.id" class="holder-chip" :class="h.career_type">
              {{ h.character_name }}
              <span class="holder-stage">Lv.{{ h.current_stage }}</span>
            </span>
          </div>
        </div>
      </a-card>
    </div>
    <a-empty v-else>
      <template #description>
        <div style="max-width:360px;margin:0 auto;">
          <p style="margin-bottom:8px;">暂无职业体系</p>
          <p style="font-size:12px;color:#999;">
            部分题材（虐恋、纯言情、古风宫斗等）不需要力量/职业进阶体系，
            AI 初始化时会自动判断并跳过。如需手动创建，点击下方按钮。
          </p>
        </div>
      </template>
    </a-empty>

    <!-- 添加 -->
    <a-modal v-model:open="showAdd" title="添加职业" width="480px">
      <a-form layout="vertical">
        <a-form-item label="名称"><a-input v-model:value="newCareer.name" /></a-form-item>
        <a-form-item label="类型">
          <a-select v-model:value="newCareer.career_type">
            <a-select-option label="主职业" value="main" />
            <a-select-option label="副职业" value="sub" />
          </a-select>
        </a-form-item>
        <a-form-item label="分类"><a-input v-model:value="newCareer.category" placeholder="战斗 / 辅助 / 生产 / 特殊" /></a-form-item>
        <a-form-item label="描述"><a-textarea v-model:value="newCareer.description" :rows="3" /></a-form-item>
      </a-form>
      <template #footer>
        <a-button @click="showAdd = false">取消</a-button>
        <a-button type="primary" @click="onAdd">添加</a-button>
      </template>
    </a-modal>

    <!-- 追加/生成职业体系 -->
    <a-modal v-model:open="showGen" :title="(careers||[]).length ? '追加生成职业' : 'AI 生成职业体系'" width="460px">
      <a-alert
        v-if="(careers||[]).length"
        message="已有职业将保留，本次为追加生成（不覆盖）。AI 会避开已有的职业。"
        type="info" show-icon :closable="false" style="margin-bottom:12px"
      />
      <a-form layout="vertical">
        <a-form-item label="生成数量">
          <a-input-number v-model:value="genCount" :min="1" :max="10" style="width:100%" />
        </a-form-item>
        <a-form-item label="职业类型">
          <a-radio-group v-model:value="genType">
            <a-radio value="all">全部（主+副）</a-radio>
            <a-radio value="main">仅主职业</a-radio>
            <a-radio value="sub">仅副职业</a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item label="额外需求（可选）">
          <a-textarea v-model:value="genReq" :rows="2" placeholder="如：需要一个炼丹师体系、需要杀手类职业..." />
        </a-form-item>
      </a-form>
      <template #footer>
        <a-button @click="showGen = false">取消</a-button>
        <a-button type="primary" :loading="generating" @click="doGenerate">{{ generating ? '生成中…' : '开始生成' }}</a-button>
      </template>
    </a-modal>

    <!-- 编辑（含进阶阶段 + 能力 动态编辑）-->
    <a-modal :open="!!editing" @update:open="(v: any) => { if (!v) editing = null }" title="编辑职业" width="680px" v-if="editing">
      <a-form layout="vertical">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
          <a-form-item label="名称"><a-input v-model:value="editForm.name" /></a-form-item>
          <a-form-item label="分类"><a-input v-model:value="editForm.category" placeholder="战斗/辅助/生产/特殊" /></a-form-item>
        </div>
        <a-form-item label="类型">
          <a-select v-model:value="editForm.career_type">
            <a-select-option label="主职业" value="main" />
            <a-select-option label="副职业" value="sub" />
          </a-select>
        </a-form-item>
        <a-form-item label="描述"><a-textarea v-model:value="editForm.description" :rows="3" /></a-form-item>

        <!-- 进阶阶段编辑器 -->
        <a-divider orientation="left">📌 进阶阶段（{{ editForm.stages.length }}）</a-divider>
        <div v-for="(s, i) in editForm.stages" :key="i" class="stage-edit-row">
          <div class="stage-edit-head">
            <span class="stage-edit-no">阶段 {{ i + 1 }}</span>
            <div class="stage-edit-ops">
              <a-button size="small" :disabled="i === 0" @click="moveStage(i, -1)">↑</a-button>
              <a-button size="small" :disabled="i === editForm.stages.length - 1" @click="moveStage(i, 1)">↓</a-button>
              <a-button size="small" danger @click="removeStage(i)">删除</a-button>
            </div>
          </div>
          <a-input v-model:value="s.name" placeholder="阶段名称（如：炼气期、初窥门径）" style="margin-bottom:6px" />
          <a-textarea v-model:value="s.description" :rows="2" placeholder="阶段描述" style="margin-bottom:6px" />
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
            <a-input v-model:value="s.requirement" placeholder="突破要求（如：需感悟天地）" />
            <a-input v-model:value="s.ability" placeholder="获得能力（如：可御剑飞行）" />
          </div>
        </div>
        <a-button type="dashed" block style="margin-top:8px" @click="addStage">+ 添加阶段</a-button>

        <!-- 能力编辑器 -->
        <a-divider orientation="left">✨ 特殊能力（{{ editForm.abilities.length }}）</a-divider>
        <div class="ability-edit-list">
          <div v-for="(a, i) in editForm.abilities" :key="i" class="ability-edit-row">
            <a-input v-model:value="a.name" placeholder="能力名称" style="flex:1" />
            <a-button size="small" danger @click="removeAbility(i)">删除</a-button>
          </div>
        </div>
        <a-input-search v-model:value="newAbility" placeholder="输入能力名称后回车添加" enter-button="添加" @search="addAbility" style="margin-top:6px" />
      </a-form>
      <template #footer>
        <a-button @click="editing = null">取消</a-button>
        <a-button type="primary" @click="onSave">保存</a-button>
      </template>
    </a-modal>
  </div>
</template>

<style scoped>
.type-tabs { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.type-tabs .cnt { margin-left: 4px; font-size: 12px; color: #999; }
.career-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(400px, 1fr)); gap: 16px; }
.card-head { display: flex; justify-content: space-between; align-items: center; padding-bottom: 10px; border-bottom: 1px solid #f0f0f0; margin-bottom: 10px; }
.head-left { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.career-icon { font-size: 20px; }
.career-name { font-size: 16px; font-weight: 600; }
.head-actions { display: flex; gap: 4px; flex-shrink: 0; }
.career-desc { font-size: 13px; color: #595959; line-height: 1.7; margin-bottom: 12px; }
.career-section { margin-top: 12px; }
.section-title { font-size: 12px; color: #4D8088; font-weight: 600; margin-bottom: 8px; }
.stage-timeline { display: flex; flex-wrap: wrap; gap: 4px; align-items: stretch; }
.stage-item { display: flex; align-items: center; gap: 8px; background: #EAF0F1; padding: 6px 12px; border-radius: 6px; margin-bottom: 4px; }
.stage-index { width: 22px; height: 22px; border-radius: 50%; background: #4D8088; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; flex-shrink: 0; }
.stage-body { display: flex; flex-direction: column; gap: 2px; }
.stage-name { font-size: 13px; font-weight: 600; color: #2B2B2B; }
.stage-detail { font-size: 11px; color: #8C8C8C; max-width: 200px; }
.stage-arrow { color: #B5C7CB; margin: 0 4px; }
.ability-list { display: flex; flex-wrap: wrap; gap: 6px; }
.holder-list { display: flex; flex-wrap: wrap; gap: 6px; }
.holder-chip { font-size: 12px; padding: 2px 8px; border-radius: 4px; background: #F8F6F1; color: #595959; display: inline-flex; align-items: center; gap: 4px; }
.holder-chip.main { background: #FFF7E6; color: #D49A4E; }
.holder-stage { font-size: 10px; opacity: 0.8; }
.stage-edit-row { background: #F8F6F1; border-radius: 8px; padding: 10px; margin-bottom: 10px; }
.stage-edit-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.stage-edit-no { font-size: 13px; font-weight: 600; color: #4D8088; }
.stage-edit-ops { display: flex; gap: 4px; }
.ability-edit-list { display: flex; flex-direction: column; gap: 6px; }
.ability-edit-row { display: flex; gap: 6px; align-items: center; }
</style>
