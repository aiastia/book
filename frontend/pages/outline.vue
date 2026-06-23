<script setup lang="ts">
import { useProjectApi } from '~/composables/useProjectApi'
import { useProject } from '~/composables/useProject'
useHead({ title: '故事大纲 — 墨语' })
const { currentProjectId } = useProject()
if (!currentProjectId.value) await navigateTo('/books')
const api = useProjectApi()
const msg = useMessage()
const { data: project } = await api.getProject()
const { data: outlines, refresh } = await api.getOutlines()

const generating = ref(false)
const genCount = ref(10)
const showGen = ref(false)
const editing = ref<any>(null)
const editForm = reactive({ title: '', summary: '', emotion: '', goal: '', key_points_text: '', characters_text: '' })

// 续写弹窗
const showContinue = ref(false)
const continueForm = reactive({
  chapter_count: 5,
  story_direction: '',
  plot_stage: '',
  narrative_pov: '',  // 空 = 按小说设定（项目默认）
  other_requirements: '',
  ai_model: '',       // 空 = 使用默认模型
})
// 续写章节数固定选项
const chapterCountOptions = [5, 10, 20, 40]
// 远程模型列表（动态拉取）
const remoteModels = ref<Array<{ id: string; owned_by: string }>>([])
const defaultModelName = ref('')
const loadingModels = ref(false)

// 项目默认叙事视角（用于「按小说设定」placeholder 显示）
const projectDefaultPov = computed(() => project.value?.narrative_pov || '第三人称')

// 新角色检测（大纲续写后）
const showNewChars = ref(false)
const newCharNames = ref<string[]>([])
const generatingChars = ref(false)

const isOneToMany = computed(() => (project.value?.outline_mode || 'one_to_one') === 'one_to_many')
const modeLabel = computed(() => isOneToMany.value ? '细化模式 (1→N)' : '传统模式 (1→1)')
const unitLabel = computed(() => isOneToMany.value ? '卷' : '章')

// 展开折叠
const expandedItems = ref<Set<number>>(new Set())
function toggleExpand(id: number) {
  if (expandedItems.value.has(id)) expandedItems.value.delete(id)
  else expandedItems.value.add(id)
}

// 展开为多章
const expanding = ref(false)
const showExpand = ref(false)
const expandTarget = ref<any>(null)
const expandCount = ref(3)
const showPreview = ref(false)
const previewData = ref<any>(null)

// 解析 structure（含 scenes/characters/key_events 等额外字段）
function parseStructure(o: any): any {
  if (o.structure && typeof o.structure === 'object') return o.structure
  // 尝试从 JSON 字符串解析
  if (typeof o.structure === 'string') {
    try { return JSON.parse(o.structure) } catch { return {} }
  }
  return {}
}
function getCharacters(o: any): string[] {
  const s = parseStructure(o)
  const chars = o.characters || s.characters || []
  if (Array.isArray(chars)) return chars.map((c: any) => typeof c === 'string' ? c : c.name || '')
  return []
}
function getScenes(o: any): any[] {
  const s = parseStructure(o)
  return s.scenes || []
}
function getSummaryPreview(o: any): string {
  const summary = o.summary || ''
  const isExpanded = expandedItems.value.has(o.id)
  if (isExpanded || summary.length <= 120) return summary
  return summary.substring(0, 120) + '…'
}

async function onGenerate() {
  generating.value = true
  try {
    const { task_id } = await api.generateOutlinesAsync(genCount.value)
    const { trackTask } = useBackgroundTasks()
    trackTask(task_id, 'outline_new', `生成${genCount.value}章大纲`)
    showGen.value = false
    msg.success('大纲生成任务已提交，可在右下角查看进度')
    // 轮询完成后刷新
    setTimeout(() => refresh(), 5000)
  }
  catch (e: any) { msg.error('生成失败：' + formatError(e)) }
  finally { generating.value = false }
}

function openContinue() {
  // 检查是否已有大纲
  if (!outlines.value || outlines.value.length === 0) {
    // 没有大纲，打开生成弹窗
    showGen.value = true
  } else {
    // 有大纲，打开续写弹窗
    continueForm.chapter_count = 5
    continueForm.story_direction = ''
    continueForm.plot_stage = ''
    continueForm.narrative_pov = ''   // 空表示按小说设定
    continueForm.other_requirements = ''
    continueForm.ai_model = ''        // 空表示使用默认模型
    showContinue.value = true
    // 动态拉取远程模型列表（异步，不阻塞弹窗）
    loadRemoteModels()
  }
}

async function loadRemoteModels() {
  if (remoteModels.value.length) return  // 已加载过
  loadingModels.value = true
  try {
    const r = await api.fetchDefaultRemoteModels()
    remoteModels.value = r.models || []
    defaultModelName.value = r.default_model || ''
  } catch (e: any) {
    // 拉取失败不阻塞，用户可仍用默认模型
    console.warn('拉取模型列表失败', e)
  } finally {
    loadingModels.value = false
  }
}

async function onContinue() {
  generating.value = true
  try {
    const params: any = { chapter_count: continueForm.chapter_count }
    if (continueForm.story_direction) params.story_direction = continueForm.story_direction
    if (continueForm.plot_stage) params.plot_stage = continueForm.plot_stage
    if (continueForm.narrative_pov) params.narrative_pov = continueForm.narrative_pov
    if (continueForm.other_requirements) params.other_requirements = continueForm.other_requirements
    if (continueForm.ai_model) params.ai_model = continueForm.ai_model

    const { task_id } = await api.continueOutlinesAsync(params)
    const { trackTask } = useBackgroundTasks()
    trackTask(task_id, 'outline_continue', `续写${continueForm.chapter_count}章大纲`)
    showContinue.value = false
    msg.success('大纲续写任务已提交，可在右下角查看进度')
    setTimeout(() => refresh(), 5000)
  }
  catch (e: any) { msg.error('续写失败：' + formatError(e)) }
  finally { generating.value = false }
}
async function onGenerateNewChars() {
  generatingChars.value = true
  try {
    for (const name of newCharNames.value) {
      await api.autoGenerateCharacter({ specification: `请生成一个名为「${name}」的角色` })
    }
    msg.success(`已生成 ${newCharNames.value.length} 个新角色`)
    showNewChars.value = false
    newCharNames.value = []
  } catch (e: any) { msg.error('角色生成失败：' + formatError(e)) }
  finally { generatingChars.value = false }
}
function openEdit(o: any) {
  editing.value = o
  const chars = getCharacters(o)
  Object.assign(editForm, {
    title: o.title || '',
    summary: o.summary || '',
    emotion: o.emotion || '',
    goal: o.goal || '',
    key_points_text: (o.key_points || []).join('\n'),
    characters_text: chars.join('、'),
  })
}
async function onSave() {
  try {
    // 保留原 structure 数据，不丢数据
    const orig = editing.value
    const origStructure = parseStructure(orig)
    await api.updateOutline(orig.id, {
      title: editForm.title,
      summary: editForm.summary,
      emotion: editForm.emotion,
      goal: editForm.goal,
      key_points: editForm.key_points_text.split('\n').filter(s => s.trim()),
      characters: editForm.characters_text.split(/[、,，\s]+/).filter(s => s.trim()),
      scenes: getScenes(orig),  // 保留原 scenes
      structure: { ...origStructure, title: editForm.title, summary: editForm.summary, emotion: editForm.emotion, goal: editForm.goal },
      chapter_number: orig.chapter_number,
    })
    await refresh(); editing.value = null; msg.success('已保存')
  } catch (e: any) { msg.error('保存失败：' + formatError(e)) }
}
async function onDelete(id: number) {
  if (!await msg.confirm('确认删除？')) return
  try { await api.deleteOutline(id); await refresh(); msg.success('已删除') }
  catch (e: any) { msg.error('删除失败：' + formatError(e)) }
}

function openExpand(o: any) {
  if (o.has_chapters) { viewExpansion(o); return }
  expandTarget.value = o
  expandCount.value = 3
  showExpand.value = true
}
async function doExpand() {
  if (!expandTarget.value) return
  expanding.value = true
  try {
    const r = await api.expandOutline(expandTarget.value.id, { target_chapter_count: expandCount.value })
    await refresh(); showExpand.value = false
    msg.success(`已展开为 ${r.count} 章`)
  } catch (e: any) { msg.error('展开失败：' + formatError(e)) }
  finally { expanding.value = false }
}
async function viewExpansion(o: any) {
  try { previewData.value = { outline: o, ...await api.getOutlineChapters(o.id) }; showPreview.value = true }
  catch (e: any) { msg.error('加载失败：' + formatError(e)) }
}
async function deleteExpansion() {
  if (!previewData.value) return
  if (!await msg.confirm(`确认删除此大纲展开的所有 ${previewData.value.chapter_count} 章？`)) return
  try { await api.deleteOutlineChapters(previewData.value.outline.id); await refresh(); showPreview.value = false; msg.success('已删除') }
  catch (e: any) { msg.error('删除失败：' + formatError(e)) }
}
</script>

<template>
  <div class="outline-page">
    <div class="page-actions">
      <a-tag :color="isOneToMany ? 'green' : 'blue'" style="font-size:13px;padding:2px 12px;">{{ modeLabel }}</a-tag>
      <a-button type="primary" :loading="generating" @click="openContinue">
        {{ outlines && outlines.length ? '续写大纲' : 'AI 生成大纲' }}
      </a-button>
    </div>

    <div v-if="outlines && outlines.length" class="outline-list">
      <div v-for="o in outlines" :key="o.id" class="outline-item">
        <!-- 标题区 -->
        <div class="item-head">
          <span class="item-no">第{{ o.chapter_number }}{{ unitLabel }}</span>
          <span class="item-title">{{ o.title || '无标题' }}</span>
          <template v-if="isOneToMany">
            <a-tag v-if="o.has_chapters" color="success" size="small">✓ 展开{{ o.chapter_count }}章</a-tag>
            <a-tag v-else color="default" size="small">未展开</a-tag>
          </template>
          <div class="item-actions">
            <a-button v-if="isOneToMany" type="link" size="small" @click="openExpand(o)">{{ o.has_chapters ? '查看' : '展开' }}</a-button>
            <a-button type="link" size="small" @click="toggleExpand(o.id)">{{ expandedItems.has(o.id) ? '收起' : '展开' }}</a-button>
            <a-button type="link" size="small" @click="openEdit(o)">编辑</a-button>
            <a-button type="link" danger size="small" @click="onDelete(o.id)">删除</a-button>
          </div>
        </div>

        <!-- 大纲内容（分区） -->
        <div class="item-body">
          <!-- 梗概 -->
          <div class="content-section">
            <div class="section-label">📝 大纲梗概</div>
            <div class="section-text">{{ getSummaryPreview(o) }}</div>
          </div>

          <!-- 涉及角色（从 structure 解析） -->
          <div v-if="getCharacters(o).length" class="content-section chars">
            <div class="section-label">👥 涉及角色（{{ getCharacters(o).length }}）</div>
            <div class="char-tags">
              <a-tag v-for="(c, i) in getCharacters(o)" :key="i" color="purple" size="small">{{ c }}</a-tag>
            </div>
          </div>

          <!-- 关键情节点 -->
          <div v-if="o.key_points && o.key_points.length" class="content-section">
            <div class="section-label">🔑 关键情节点（{{ o.key_points.length }}）</div>
            <div v-if="o.emotion" class="emotion-tag">
              <a-tag size="small" color="orange">情绪基调：{{ o.emotion }}</a-tag>
            </div>
            <div class="key-points">
              <div v-for="(p, i) in o.key_points" :key="i" class="kp-item">
                <span class="kp-dot">{{ i + 1 }}</span>
                <span>{{ typeof p === 'string' ? p : p.content || p.point || p.event || JSON.stringify(p) }}</span>
              </div>
            </div>
          </div>

          <!-- 场景（从 structure 解析，展开时显示） -->
          <div v-if="expandedItems.has(o.id) && getScenes(o).length" class="content-section">
            <div class="section-label">🎬 场景（{{ getScenes(o).length }}）</div>
            <div class="scene-list">
              <div v-for="(sc, i) in getScenes(o)" :key="i" class="scene-item">
                <span class="scene-title">{{ sc.scene_title || sc.title || `场景${i+1}` }}</span>
                <span v-if="sc.scene_desc || sc.desc" class="scene-desc">{{ sc.scene_desc || sc.desc }}</span>
              </div>
            </div>
          </div>

          <!-- 写作目标 -->
          <div v-if="o.goal" class="content-section goal-sec">
            <div class="section-label">🎯 写作目标</div>
            <div class="section-text">{{ o.goal }}</div>
          </div>
        </div>
      </div>
    </div>
    <a-empty v-else description="暂无大纲，点击 AI 生成" />

    <!-- 生成弹窗 -->
    <a-modal v-model:open="showGen" title="AI 生成大纲" width="400px">
      <a-form layout="vertical">
        <a-form-item :label="isOneToMany ? '卷数' : '章数'"><a-input-number v-model:value="genCount" :min="3" :max="30" /></a-form-item>
      </a-form>
      <template #footer><a-button @click="showGen = false">取消</a-button><a-button type="primary" :loading="generating" @click="onGenerate">生成</a-button></template>
    </a-modal>

    <!-- 续写弹窗 -->
    <a-modal v-model:open="showContinue" title="续写大纲" width="560px">
      <a-form layout="vertical">
        <a-form-item label="续写章节数">
          <a-radio-group v-model:value="continueForm.chapter_count" button-style="solid">
            <a-radio-button v-for="n in chapterCountOptions" :key="n" :value="n">{{ n }} 章</a-radio-button>
          </a-radio-group>
        </a-form-item>
        <a-form-item label="故事发展方向">
          <a-textarea v-model:value="continueForm.story_direction" :rows="3" placeholder="描述故事接下来的发展方向，例如：主角进入秘境修炼，遇到新的挑战..." />
        </a-form-item>
        <a-form-item label="情节阶段">
          <a-select v-model:value="continueForm.plot_stage" placeholder="选择当前情节阶段" allow-clear>
            <a-select-option value="开端">开端</a-select-option>
            <a-select-option value="发展">发展</a-select-option>
            <a-select-option value="高潮">高潮</a-select-option>
            <a-select-option value="转折">转折</a-select-option>
            <a-select-option value="结局">结局</a-select-option>
          </a-select>
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item :label="`叙事视角`">
              <a-select v-model:value="continueForm.narrative_pov" :placeholder="`按小说设定（${projectDefaultPov}）`" allow-clear>
                <a-select-option value="">按小说设定</a-select-option>
                <a-select-option value="第三人称">第三人称（他/她）</a-select-option>
                <a-select-option value="第一人称">第一人称（我）</a-select-option>
                <a-select-option value="全知视角">全知视角</a-select-option>
              </a-select>
              <div class="field-hint">留空使用项目默认：{{ projectDefaultPov }}</div>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="AI 模型">
              <a-select
                v-model:value="continueForm.ai_model"
                :placeholder="defaultModelName ? `使用默认（${defaultModelName}）` : '使用默认模型'"
                allow-clear
                show-search
                option-filter-prop="label"
                :loading="loadingModels"
              >
                <a-select-option value="">使用默认模型</a-select-option>
                <a-select-option v-for="m in remoteModels" :key="m.id" :value="m.id" :label="m.id">{{ m.id }}</a-select-option>
              </a-select>
              <div v-if="!remoteModels.length && !loadingModels" class="field-hint">未拉到模型列表，将使用默认模型</div>
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="其他要求">
          <a-textarea v-model:value="continueForm.other_requirements" :rows="2" placeholder="其他特殊要求，例如：需要包含战斗场景、增加感情线..." />
        </a-form-item>
      </a-form>
      <template #footer>
        <a-button @click="showContinue = false">取消</a-button>
        <a-button type="primary" :loading="generating" @click="onContinue">开始续写</a-button>
      </template>
    </a-modal>

    <!-- 编辑弹窗（含关键点/角色编辑，不丢数据）-->
    <a-modal :open="!!editing" @update:open="(v:any) => { if(!v) editing = null }" title="编辑大纲" width="560px" v-if="editing">
      <a-form layout="vertical">
        <a-form-item label="标题"><a-input v-model:value="editForm.title" /></a-form-item>
        <a-form-item label="梗概"><a-textarea v-model:value="editForm.summary" :rows="4" /></a-form-item>
        <a-form-item label="关键情节点（每行一个）"><a-textarea v-model:value="editForm.key_points_text" :rows="3" placeholder="每行一个关键情节点" /></a-form-item>
        <a-form-item label="涉及角色（用、分隔）"><a-input v-model:value="editForm.characters_text" placeholder="角色A、角色B、角色C" /></a-form-item>
        <a-row :gutter="12">
          <a-col :span="12"><a-form-item label="情绪基调"><a-input v-model:value="editForm.emotion" /></a-form-item></a-col>
          <a-col :span="12"><a-form-item label="写作目标"><a-input v-model:value="editForm.goal" /></a-form-item></a-col>
        </a-row>
      </a-form>
      <template #footer><a-button @click="editing = null">取消</a-button><a-button type="primary" @click="onSave">保存</a-button></template>
    </a-modal>

    <!-- 展开弹窗 -->
    <a-modal v-model:open="showExpand" title="展开为多章" width="440px">
      <p>将第{{ expandTarget?.chapter_number }}卷「{{ expandTarget?.title }}」展开：</p>
      <a-input-number v-model:value="expandCount" :min="2" :max="10" addon-before="章节数" style="width:100%" />
      <template #footer><a-button @click="showExpand = false">取消</a-button><a-button type="primary" :loading="expanding" @click="doExpand">{{ expanding ? '规划中…' : '展开' }}</a-button></template>
    </a-modal>

    <!-- 已展开预览 -->
    <a-modal v-model:open="showPreview" :title="`展开预览 — 第${previewData?.outline?.chapter_number}卷`" width="600px" :footer="null">
      <div v-if="previewData">
        <div style="margin-bottom:12px;">
          <a-tag color="success">已展开 {{ previewData.chapter_count }} 章</a-tag>
          <a-button danger size="small" style="margin-left:8px" @click="deleteExpansion">删除展开</a-button>
        </div>
        <div v-for="ch in (previewData.chapters || [])" :key="ch.id" class="preview-chap">
          <div class="preview-chap-head">
            <span class="preview-chap-no">第{{ ch.chapter_number }}章</span>
            <span class="preview-chap-title">{{ ch.title }}</span>
          </div>
          <div v-if="ch.expansion_plan" class="preview-plan">
            <div v-if="ch.expansion_plan.plot_summary">{{ ch.expansion_plan.plot_summary }}</div>
          </div>
        </div>
      </div>
    </a-modal>

    <!-- 新角色检测弹窗 -->
    <a-modal v-model:open="showNewChars" title="检测到新角色" width="420px">
      <p>大纲中出现了以下新角色，是否立即生成角色档案？</p>
      <div style="margin: 12px 0;">
        <a-tag v-for="name in newCharNames" :key="name" color="purple" style="margin: 2px 4px;">{{ name }}</a-tag>
      </div>
      <p style="font-size:12px;color:#8C8C8C;">生成后可在角色页面查看和编辑详细信息。</p>
      <template #footer>
        <a-button @click="showNewChars = false">跳过</a-button>
        <a-button type="primary" :loading="generatingChars" @click="onGenerateNewChars">
          {{ generatingChars ? '生成中…' : '立即生成' }}
        </a-button>
      </template>
    </a-modal>
  </div>
</template>

<style scoped>
.outline-page { display: flex; flex-direction: column; gap: 16px; }
.page-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.outline-list { display: flex; flex-direction: column; gap: 10px; }
.outline-item { background: #fff; border: 1px solid #E8E4DC; border-radius: 8px; overflow: hidden; transition: border-color .2s, box-shadow .2s; }
.outline-item:hover { border-color: #B8CDD1; box-shadow: 0 2px 12px rgba(43,43,43,0.08); }
.item-head { display: flex; align-items: center; gap: 8px; padding: 12px 16px; border-bottom: 1px solid #F5F2EB; }
.item-no { font-size: 12px; color: #4D8088; font-weight: 600; background: #EAF0F1; padding: 2px 8px; border-radius: 4px; flex-shrink: 0; }
.item-title { font-size: 15px; font-weight: 600; color: #2B2B2B; flex: 1; }
.item-actions { display: flex; flex-shrink: 0; }
.item-body { padding: 12px 16px; }
.content-section { margin-bottom: 12px; }
.content-section:last-child { margin-bottom: 0; }
.section-label { font-size: 12px; font-weight: 600; color: #8C8C8C; margin-bottom: 6px; }
.section-text { font-size: 14px; color: #595959; line-height: 1.7; }
.content-section.chars { background: #F9F0FC; border-radius: 6px; padding: 10px 12px; }
.content-section.goal-sec { background: #F0F5F5; border-radius: 6px; padding: 10px 12px; }
.char-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.key-points { display: flex; flex-direction: column; gap: 6px; }
.emotion-tag { margin-bottom: 8px; }
.field-hint { font-size: 11px; color: #999; margin-top: 4px; }
.kp-item { display: flex; gap: 8px; font-size: 13px; color: #595959; align-items: flex-start; }
.kp-dot { width: 18px; height: 18px; border-radius: 50%; background: #4D8088; color: #fff; font-size: 11px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.scene-list { display: flex; flex-direction: column; gap: 6px; }
.scene-item { background: #FAFAF7; border-radius: 6px; padding: 8px 10px; }
.scene-title { font-weight: 600; font-size: 13px; color: #2B2B2B; }
.scene-desc { font-size: 13px; color: #8C8C8C; display: block; margin-top: 2px; }
.preview-chap { background: #FAFAF7; border-radius: 6px; padding: 10px 12px; margin-bottom: 8px; }
.preview-chap-head { display: flex; gap: 8px; margin-bottom: 4px; }
.preview-chap-no { font-size: 12px; color: #4D8088; font-weight: 600; }
.preview-chap-title { font-size: 14px; }
.preview-plan { font-size: 13px; color: #595959; }
</style>
