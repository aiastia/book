<script setup lang="ts">
// 故事章节：对标参考站 — 列表项（状态/字数/评分/分析标签）+ 弹窗编辑器
import { useProjectApi } from '~/composables/useProjectApi'
import { useProject } from '~/composables/useProject'
import { apiGet } from '~/composables/useApi'
useHead({ title: '故事章节 — 墨语' })
const { currentProjectId } = useProject()
if (!currentProjectId.value) await navigateTo('/books')
const api = useProjectApi()
const msg = useMessage()
const { data: chapters, refresh: refreshList } = await api.getChapters()
const { data: outlines } = await api.getOutlines()

const editorOpen = ref(false)
const editing = ref<any>(null)
const editingContent = ref('')
const editingTitle = ref('')
const generating = ref(false)
const saving = ref(false)
const targetWords = ref(3000)
const narrativePov = ref('第三人称')
if (import.meta.client) { const s = localStorage.getItem('moyu_chapter_words'); if (s) targetWords.value = Number(s) }

// 章节分析缓存
const analysisCache = ref<Record<number, any>>({})

async function loadAnalysis(chapterNumber: number) {
  if (analysisCache.value[chapterNumber]) return analysisCache.value[chapterNumber]
  try {
    const a = await apiGet<any>(`/api/projects/${currentProjectId.value}/analyses/${chapterNumber}`).catch(() => null)
    if (a && !a.detail) analysisCache.value[chapterNumber] = a
    return a
  } catch { return null }
}

function openEditor(c: any) {
  editing.value = c
  editingTitle.value = c.title || `第${c.chapter_number}章`
  editingContent.value = ''
  apiGet<any>(`/api/projects/${currentProjectId.value}/chapters/${c.id}`).then(d => { if (d) editingContent.value = d.content || '' })
  editorOpen.value = true
}

async function onGenerate() {
  if (!editing.value) return
  generating.value = true
  try {
    await api.generateChapter(editing.value.id)
    const ch = await apiGet<any>(`/api/projects/${currentProjectId.value}/chapters/${editing.value.id}`).catch(() => null)
    if (ch) { editingContent.value = ch.content || ''; editingTitle.value = ch.title || editingTitle.value }
    await refreshList()
    msg.success(`章节生成完成！${ch?.word_count || ''} 字`)
  } catch (e:any) { msg.error('生成失败：'+formatError(e)) }
  finally { generating.value = false }
}
async function onSave() {
  if (!editing.value) return
  saving.value = true
  try { await api.updateChapter(editing.value.id, { title: editingTitle.value, content: editingContent.value, status:'completed' }); if (import.meta.client) localStorage.setItem('moyu_chapter_words', String(targetWords.value)); await refreshList(); msg.success('保存成功') }
  catch (e:any) { msg.error('保存失败：'+formatError(e)) }
  finally { saving.value = false }
}
async function createFromOutline(o: any) {
  try {
    await api.createChapter({ chapter_number: o.chapter_number, title: o.title, outline_id: o.id })
    await refreshList(); msg.success(`第${o.chapter_number}章已创建`)
  } catch (e:any) { msg.error('创建失败：'+formatError(e)) }
}
async function createNewChapter() {
  const nextNo = (chapters.value?.length||0)+1
  try { await api.createChapter({ chapter_number: nextNo, title:`第 ${nextNo} 章` }); await refreshList(); msg.success('已创建') }
  catch (e:any) { msg.error('创建失败：'+formatError(e)) }
}
async function onDelete(id:number) {
  if (!await msg.confirm('确认删除？')) return
  try { await api.deleteChapter(id); await refreshList(); msg.success('已删除') }
  catch (e:any) { msg.error('删除失败：'+formatError(e)) }
}
async function clearContent() {
  if (!editing.value || !await msg.confirm('确认清空？')) return
  try { await api.clearChapter(editing.value.id); editingContent.value=''; await refreshList() }
  catch (e: any) { msg.error('清空失败：' + formatError(e)) }
}

// 重写/局部重写应用后，重新加载章节内容
async function onRewriteApplied() {
  if (!editing.value) return
  try {
    const ch = await apiGet<any>(`/api/projects/${currentProjectId.value}/chapters/${editing.value.id}`).catch(() => null)
    if (ch) { editingContent.value = ch.content || ''; editingTitle.value = ch.title || editingTitle.value }
    await refreshList()
    msg.success('章节内容已更新')
  } catch (e: any) { msg.error('刷新失败：' + formatError(e)) }
}
// 重写/局部/去味（简化）
const showRegen = ref(false); const regenInstr = ref(''); const regenerating = ref(false)
async function onRegen() { if(!editing.value)return; regenerating.value=true; try{const r=await api.regenerateChapter(editing.value.id,{instructions:regenInstr.value,include_analysis:true});editingContent.value=r.content||'';showRegen.value=false;await refreshList();msg.success('重写完成')}catch(e:any){msg.error('重写失败：'+formatError(e))}finally{regenerating.value=false} }
const showPartial = ref(false); const partialText=ref(''); const partialInstr=ref(''); const partialResult=ref(''); const partialing=ref(false)
function openPartial(){const ta=document.querySelector('.ch-editor textarea')as any;if(ta&&ta.selectionStart!==ta.selectionEnd)partialText.value=ta.value.substring(ta.selectionStart,ta.selectionEnd);partialInstr.value='';partialResult.value='';showPartial.value=true}
async function onPartial(){if(!editing.value||!partialText.value.trim())return;partialing.value=true;try{const r=await api.partialRegenerate(editing.value.id,{selected_text:partialText.value,user_instructions:partialInstr.value});partialResult.value=r.rewritten_text||''}catch(e:any){msg.error('失败：'+formatError(e))}finally{partialing.value=false}}
function applyPartial(){if(partialResult.value&&editingContent.value.includes(partialText.value)){editingContent.value=editingContent.value.replace(partialText.value,partialResult.value);showPartial.value=false;msg.success('已应用')}}
const showDenoise=ref(false);const denoiseText=ref('');const denoiseResult=ref('');const denoisePreview=ref(false);const denoising=ref(false)
function openDenoise(){const ta=document.querySelector('.ch-editor textarea')as any;denoiseText.value=(ta&&ta.selectionStart!==ta.selectionEnd)?ta.value.substring(ta.selectionStart,ta.selectionEnd):editingContent.value;denoiseResult.value='';denoisePreview.value=false;showDenoise.value=true}
async function onDenoise(){if(!denoiseText.value.trim())return;denoising.value=true;try{const r=await api.aiDenoising({text:denoiseText.value});denoiseResult.value=r.processed_text||'';denoisePreview.value=true}catch(e:any){msg.error('失败：'+formatError(e))}finally{denoising.value=false}}
function applyDenoise(){editingContent.value=denoiseResult.value;showDenoise.value=false;msg.success('已应用')}

// ===== 内嵌阅读器（带标注，合并 chapter-reader 功能）=====
const readerOpen = ref(false)
const readerChapter = ref<any>(null)
const readerAnnotations = ref<any[]>([])
const readerSummary = ref<any>({})
const readerLoading = ref(false)
const readerActiveAnn = ref<any>(null)
const readerShowSidebar = ref(true)
const readerExpandedGroups = ref(true)

const readerTypeMeta: Record<string, { label: string; color: string; icon: string }> = {
  hook: { label: '剧情钩子', color: '#C75B5B', icon: '🎣' },
  foreshadow: { label: '伏笔', color: '#1677FF', icon: '🔮' },
  plot_point: { label: '关键情节', color: '#52A569', icon: '⭐' },
  character_event: { label: '角色事件', color: '#D49A4E', icon: '👤' },
}
const readerGroups = computed(() => {
  const groups: Record<string, any[]> = { hook: [], foreshadow: [], plot_point: [], character_event: [] }
  for (const a of (readerAnnotations.value || [])) {
    if (a && a.type && groups[a.type]) groups[a.type].push(a)
  }
  return (Object.keys(readerTypeMeta) as string[])
    .map(type => ({ type, label: readerTypeMeta[type].label, icon: readerTypeMeta[type].icon, color: readerTypeMeta[type].color, items: groups[type] }))
    .filter(g => g.items.length > 0)
})

async function openReader(c: any) {
  readerOpen.value = true
  readerLoading.value = true
  readerActiveAnn.value = null
  readerAnnotations.value = []
  readerSummary.value = {}
  try {
    // 章节详情
    const ch = await apiGet<any>(`/api/projects/${currentProjectId.value}/chapters/${c.id}`)
    readerChapter.value = ch
    // 标注
    const r = await api.getAnnotations(c.id)
    readerAnnotations.value = r.annotations || []
    readerSummary.value = r.summary || {}
  } catch (e: any) {
    msg.error('加载失败：' + formatError(e))
  } finally {
    readerLoading.value = false
  }
}
// 阅读器内翻章
async function readerNavigate(direction: -1 | 1) {
  const list = chapters.value || []
  const idx = list.findIndex((c: any) => c.id === readerChapter.value?.id)
  const next = list[idx + direction]
  if (next) await openReader(next)
}
function readerNavInfo() {
  const list = chapters.value || []
  const idx = list.findIndex((c: any) => c.id === readerChapter.value?.id)
  return { hasPrev: idx > 0, hasNext: idx < list.length - 1 }
}
// 阅读器内触发分析
const readerAnalyzing = ref(false)
async function readerAnalyze() {
  if (!readerChapter.value) return
  readerAnalyzing.value = true
  msg.info('正在分析，请等待…')
  try {
    await api.triggerAnalysis(readerChapter.value.id)
    // 重新加载标注
    const r = await api.getAnnotations(readerChapter.value.id)
    readerAnnotations.value = r.annotations || []
    readerSummary.value = r.summary || {}
    msg.success('分析完成，标注已更新')
  } catch (e: any) {
    msg.error('分析失败：' + formatError(e))
  } finally {
    readerAnalyzing.value = false
  }
}

const statusText=(s:string)=>({draft:'草稿',generating:'创作中',completed:'已完成'}[s]||s)
const statusColor=(s:string)=>({draft:'default',generating:'processing',completed:'success'}[s]||'default')
const createdChapterNos = computed(() => new Set((chapters.value||[]).map(c=>c.chapter_number)))
</script>

<template>
  <div class="ch-page">
    <div class="page-actions">
      <a-button @click="createNewChapter">+ 空白章</a-button>
      <BatchGeneratePanel :chapters="chapters || []" @done="refresh" />
    </div>
    <!-- 从大纲创建（未创建的大纲） -->
    <a-card v-if="outlines && outlines.filter(o=>!createdChapterNos.has(o.chapter_number)).length" size="small" title="从大纲创建章节" style="margin-bottom:12px">
      <div class="outline-chips">
        <a-button v-for="o in outlines.filter(o=>!createdChapterNos.has(o.chapter_number))" :key="o.id" size="small" @click="createFromOutline(o)">
          第{{ o.chapter_number }}章 {{ o.title }}
        </a-button>
      </div>
    </a-card>

    <div v-if="chapters && chapters.length" class="ch-list">
      <div v-for="c in chapters" :key="c.id" class="ch-row" @click="openEditor(c)">
        <div class="ch-row-icon">📄</div>
        <div class="ch-row-main">
          <div class="ch-row-head">
            <span class="ch-row-title">第{{ c.chapter_number }}章：{{ c.title||'无标题' }}</span>
            <a-tag :color="statusColor(c.status)" size="small">{{ statusText(c.status) }}</a-tag>
            <a-tag v-if="c.word_count" color="success" size="small">{{ (c.word_count||0).toLocaleString() }}字</a-tag>
            <a-tag v-if="c.quality_alert && c.quality_alert.includes('consistency_issue')" color="red" size="small">⚠️矛盾</a-tag>
            <a-tag v-if="c.quality_alert && c.quality_alert.includes('low_score')" color="orange" size="small">低分</a-tag>
            <a-tag v-if="c.quality_score" color="processing" size="small">评分{{ c.quality_score }}</a-tag>
          </div>
          <div v-if="c.summary" class="ch-row-summary">{{ c.summary.substring(0,80) }}</div>
        </div>
        <div class="ch-row-actions" @click.stop>
          <a-button type="text" size="small" @click="openEditor(c)">编辑</a-button>
          <a-button type="text" size="small" @click.stop="openReader(c)">📖 阅读</a-button>
          <a-button type="text" size="small" danger @click="onDelete(c.id)">删除</a-button>
        </div>
      </div>
    </div>
    <a-empty v-else description="暂无章节" />

    <!-- 编辑器 -->
    <a-modal v-model:open="editorOpen" :title="`编辑：第${editing?.chapter_number}章`" width="90%" :style="{top:'20px'}" :footer="null" :destroyOnClose="true">
      <div v-if="editing" class="editor">
        <div class="editor-bar">
          <a-input v-model:value="editingTitle" size="large" style="flex:1;font-weight:600" />
          <a-button type="primary" :loading="generating" @click="onGenerate">{{ generating?'AI创作中…':'⚡ AI创作' }}</a-button>
          <ClientOnly>
            <ChapterRewritePanel :chapter-id="editing.id" :chapter-content="editingContent" @applied="onRewriteApplied" />
            <template #fallback><a-button disabled>✏️ 重写/润色</a-button></template>
          </ClientOnly>
          <a-button :loading="denoising" @click="openDenoise">去AI味</a-button>
          <a-button type="primary" :loading="saving" @click="onSave">保存</a-button>
          <a-button @click="clearContent">清空</a-button>
        </div>
        <div class="editor-opts">
          <span>视角：<a-select v-model:value="narrativePov" size="small" style="width:110px"><a-select-option label="第三人称" value="第三人称" /><a-select-option label="第一人称" value="第一人称" /></a-select></span>
          <span>目标字数：<a-input-number v-model:value="targetWords" :min="500" :max="10000" :step="100" size="small" style="width:110px" /></span>
        </div>
        <div class="ch-editor"><a-textarea v-model:value="editingContent" :rows="18" placeholder="点击AI创作生成正文..." /></div>
        <div class="editor-foot">字数：{{ editingContent.length.toLocaleString() }}</div>
      </div>
    </a-modal>

    <a-modal v-model:open="showRegen" title="重写全章" width="500px"><a-textarea v-model:value="regenInstr" :rows="4" placeholder="修改要求" /><template #footer><a-button @click="showRegen=false">取消</a-button><a-button type="primary" :loading="regenerating" @click="onRegen">重写</a-button></template></a-modal>
    <a-modal v-model:open="showPartial" title="局部改写" width="600px"><a-textarea v-model:value="partialText" :rows="5" /><a-textarea v-model:value="partialInstr" :rows="2" placeholder="要求" style="margin-top:8px" /><div v-if="partialResult" style="margin-top:8px"><strong style="color:#4D8088">结果</strong><div style="background:#F0F5F5;padding:8px;border-radius:6px;margin-top:4px;white-space:pre-wrap">{{ partialResult }}</div><a-button type="primary" size="small" @click="applyPartial" style="margin-top:4px">应用替换</a-button></div><template #footer><a-button @click="showPartial=false">取消</a-button><a-button type="primary" :loading="partialing" @click="onPartial">AI改写</a-button></template></a-modal>
    <a-modal v-model:open="showDenoise" title="去AI味" width="600px"><div v-if="!denoisePreview"><a-textarea v-model:value="denoiseText" :rows="6" /></div><div v-else><strong style="color:#4D8088">结果</strong><div style="background:#F0F5F5;padding:8px;border-radius:6px;margin-top:4px;white-space:pre-wrap">{{ denoiseResult }}</div></div><template #footer><a-button @click="showDenoise=false">{{denoisePreview?'关闭':'取消'}}</a-button><a-button v-if="denoisePreview" type="primary" @click="applyDenoise">应用</a-button><a-button v-else type="primary" :loading="denoising" @click="onDenoise">润色</a-button></template></a-modal>

    <!-- 内嵌阅读器（带标注，合并 chapter-reader 功能）-->
    <a-modal v-model:open="readerOpen" :width="1100" :title="readerChapter ? `📖 阅读：第${readerChapter.chapter_number}章 · ${readerChapter.title}` : '阅读'" :style="{ top: '10px' }" :footer="null" :destroyOnClose="true">
      <div v-if="readerLoading" style="text-align:center;padding:60px;color:#8C8C8C;">加载中…</div>
      <div v-else-if="readerChapter" class="reader-layout">
        <!-- 正文（带标注） -->
        <div class="reader-main">
          <div class="reader-toolbar-bar">
            <a-button size="small" :disabled="!readerNavInfo().hasPrev" @click="readerNavigate(-1)">← 上一章</a-button>
            <a-button size="small" type="link" @click="readerShowSidebar = !readerShowSidebar">{{ readerShowSidebar ? '隐藏标注' : '显示标注' }}</a-button>
            <a-button size="small" :loading="readerAnalyzing" @click="readerAnalyze">🤖 {{ readerAnalyzing ? '分析中…' : (readerSummary.has_analysis ? '重新分析' : '分析此章') }}</a-button>
            <a-button size="small" :disabled="!readerNavInfo().hasNext" style="margin-left:auto" @click="readerNavigate(1)">下一章 →</a-button>
          </div>
          <ClientOnly>
            <div class="reader-content-box">
              <AnnotatedText :content="readerChapter.content || ''" :annotations="readerAnnotations" @select="(a: any) => readerActiveAnn = a" />
            </div>
          </ClientOnly>
        </div>
        <!-- 标注侧栏 -->
        <div v-if="readerShowSidebar" class="reader-side">
          <div class="reader-side-title">
            <span>本章标注</span>
            <span v-if="readerSummary.total" class="reader-side-count">{{ readerSummary.total }}</span>
          </div>
          <div v-if="readerSummary.total" class="reader-side-stats">
            <span v-for="g in readerGroups" :key="'s'+g.type" :style="{ color: g.color }">{{ g.icon }} {{ g.items.length }}</span>
          </div>
          <div v-for="g in readerGroups" :key="g.type" class="reader-side-group">
            <div class="reader-group-title" :style="{ color: g.color }">{{ g.icon }} {{ g.label }}（{{ g.items.length }}）</div>
            <div v-for="(a, i) in g.items" :key="i" class="reader-ann-item" :class="{ active: readerActiveAnn === a }" :style="{ borderLeftColor: g.color }" @click="readerActiveAnn = a">
              <div class="reader-ann-title">{{ a.title }}</div>
              <div class="reader-ann-content">{{ a.content }}</div>
            </div>
          </div>
          <div v-if="!readerSummary.total" class="reader-no-annot">无标注{{ readerSummary.has_analysis === false ? '（此章节尚未分析）' : '' }}</div>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<style scoped>
.ch-page { display:flex; flex-direction:column; gap:12px; }
.page-actions { display:flex; gap:8px; }
.outline-chips { display:flex; flex-wrap:wrap; gap:6px; }
.ch-list { display:flex; flex-direction:column; gap:8px; }
.ch-row { display:flex; align-items:flex-start; gap:10px; padding:14px 16px; background:#fff; border:1px solid #E8E4DC; border-radius:8px; cursor:pointer; transition:all .2s; }
.ch-row:hover { border-color:#B8CDD1; box-shadow:0 2px 8px rgba(43,43,43,0.06); }
.ch-row-icon { font-size:20px; flex-shrink:0; }
.ch-row-main { flex:1; min-width:0; }
.ch-row-head { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.ch-row-title { font-size:15px; font-weight:500; }
.ch-row-summary { font-size:13px; color:#8C8C8C; margin-top:4px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.ch-row-actions { display:flex; gap:2px; flex-shrink:0; }
.editor { display:flex; flex-direction:column; gap:10px; }
.editor-bar { display:flex; gap:6px; flex-wrap:wrap; align-items:center; }
.editor-opts { display:flex; gap:20px; font-size:13px; color:#595959; }
.editor-foot { font-size:12px; color:#8C8C8C; text-align:right; }
/* 内嵌阅读器 */
.reader-layout { display: grid; grid-template-columns: 1fr 280px; gap: 14px; height: calc(100vh - 160px); }
.reader-main { display: flex; flex-direction: column; gap: 10px; overflow: hidden; }
.reader-toolbar-bar { display: flex; align-items: center; gap: 8px; }
.reader-content-box { background: #fff; border-radius: 8px; padding: 24px 32px; overflow-y: auto; flex: 1; border: 1px solid #E8E4DC; font-size: 15px; line-height: 2; }
.reader-side { background: #fff; border-radius: 8px; padding: 12px; overflow-y: auto; border: 1px solid #E8E4DC; }
.reader-side-title { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; color: #4D8088; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid #F0EDE6; }
.reader-side-count { background: #4D8088; color: #fff; font-size: 11px; padding: 1px 7px; border-radius: 10px; }
.reader-side-stats { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; font-size: 12px; font-weight: 600; }
.reader-side-group { margin-bottom: 12px; }
.reader-group-title { font-size: 12px; font-weight: 600; margin-bottom: 6px; }
.reader-ann-item { padding: 8px 10px; background: #FAFAF7; border-radius: 6px; border-left: 3px solid #B5C7CB; margin-bottom: 6px; cursor: pointer; }
.reader-ann-item:hover { background: #F0EDE6; }
.reader-ann-item.active { background: #EAF0F1; }
.reader-ann-title { font-size: 12px; font-weight: 600; color: #2B2B2B; margin-bottom: 3px; }
.reader-ann-content { font-size: 12px; color: #595959; line-height: 1.5; }
.reader-no-annot { font-size: 13px; color: #8C8C8C; text-align: center; padding: 24px 0; }
</style>
