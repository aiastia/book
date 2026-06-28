<script setup lang="ts">
// 我的书架：拟物书本卡片 + 删除/导出/导入 + 新建向导（AI一键生成世界观/角色/大纲）
import { useBookApi } from '~/composables/useBookApi'
import { useProject } from '~/composables/useProject'
definePageMeta({ layout: 'default' })
useHead({ title: '我的书架 — 墨语' })
const msg = useMessage()
const api = useBookApi()
const { selectProject, createProject: selectAndCreate } = useProject()
const { data: projects, refresh } = await api.listBooks()

// 检查 AI 模型是否已配置
const aiConfigured = ref<boolean | null>(null)
;(async () => {
  try {
    const models = await api.listAiModels()
    aiConfigured.value = Array.isArray(models) && models.length > 0
  } catch { aiConfigured.value = false }
})()

// ===== 模式筛选 =====
const filterMode = ref<'all' | 'one_to_one' | 'one_to_many'>('all')
const filteredProjects = computed(() => {
  if (filterMode.value === 'all') return projects.value || []
  return (projects.value || []).filter(p => (p.outline_mode || 'one_to_one') === filterMode.value)
})

// ===== 删除 / 导出 / 导入 =====
async function onDelete(p: any, e: Event) {
  e.stopPropagation()
  if (!await msg.confirm(`确认删除《${p.title}》？所有章节/角色/大纲将一并删除，不可恢复。`)) return
  try { await api.deleteProjectById(p.id); await refresh(); msg.success('已删除') }
  catch (e: any) { msg.error('删除失败：' + formatError(e)) }
}
async function onExport(p: any, format: string = 'json') {
  try {
    if (format === 'txt') {
      // TXT 整书下载
      const token = (import.meta.client && localStorage.getItem('moyu_token')) || ''
      const downloadUrl = api.exportProject(p.id, 'txt') as string
      const resp = await fetch(downloadUrl, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!resp.ok) throw new Error('导出失败')
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `${p.title}.txt`; a.click()
      URL.revokeObjectURL(url)
      msg.success('已导出 TXT')
    } else {
      const data = await api.exportProject(p.id)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `${p.title}.json`; a.click()
      URL.revokeObjectURL(url)
      msg.success('已导出（全量 JSON）')
    }
  } catch (e: any) { msg.error('导出失败：' + formatError(e)) }
}

const showImport = ref(false)
const importText = ref('')
async function onImport() {
  try {
    const data = JSON.parse(importText.value)
    await api.importProject(data)
    showImport.value = false; importText.value = ''
    await refresh(); msg.success('导入成功')
  } catch (e: any) { msg.error('导入失败：' + formatError(e)) }
}
function onImportFile(e: any) {
  const file = e.target.files[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => { importText.value = String(reader.result); showImport.value = true }
  reader.readAsText(file)
}

// ===== 新建向导 =====
const showCreate = ref(false)
const genres = ['玄幻', '都市', '科幻', '言情', '历史', '武侠', '游戏', '悬疑', '修仙', '末世', '无限流', '二次元', '同人', '其他']
const wizard = reactive({
  title: '', genre: '玄幻', synopsis: '', theme: '',
  outline_mode: 'one_to_many', narrative_pov: '第三人称',
  character_count: 5, target_word_count: 100000, protagonist_name: '',
  chapter_count: 3,
})
const creating = ref(false)
const genStep = ref('')  // 生成进度提示

// 使用统一的后台任务管理
const { startLegacy } = useBackgroundTasks()

async function onCreate() {
  if (!wizard.title.trim()) { msg.warning('请输入书名'); return }
  creating.value = true
  try {
    genStep.value = '创建项目...'
    // 1. 创建项目（带完整字段）
    const proj = await apiPost<any>('/api/projects', {
      title: wizard.title, genre: wizard.genre, synopsis: wizard.synopsis,
      narrative_pov: wizard.narrative_pov, target_word_count: wizard.target_word_count,
      outline_mode: wizard.outline_mode,
    })
    const pid = proj.id
    selectProject(pid, { id: pid, title: wizard.title, genre: wizard.genre })

    // 2. 提交后台初始化任务（世界观+角色+大纲异步生成，用户可自由切页）
    genStep.value = '提交生成任务...'
    try {
      const task = await apiPost<any>(`/api/projects/${pid}/init-task`,
        { protagonist_name: wizard.protagonist_name, chapter_count: wizard.chapter_count }, { timeout: 10000 })
      // 使用统一的后台任务管理，确保浮窗立即显示
      startLegacy(task.task_id)
    } catch (e: any) {
      console.warn('后台任务失败，兜底同步生成', e)
      genStep.value = '生成世界观...'
      try { await apiPost(`/api/projects/${pid}/world-core/generate`, {}, { timeout: 90000 }) } catch {}
      genStep.value = '生成角色...'
      try { await apiPost(`/api/projects/${pid}/characters/batch-generate`, { count: wizard.character_count, requirements: wizard.protagonist_name ? `主角名字：${wizard.protagonist_name}` : '' }, { timeout: 120000 }) } catch {}
      genStep.value = '生成大纲...'
      try { await apiPost(`/api/projects/${pid}/outlines/generate`, { chapter_count: wizard.chapter_count }, { timeout: 120000 }) } catch {}
    }

    genStep.value = ''
    showCreate.value = false
    msg.success('项目已创建！内容正在后台生成，你可以自由浏览')
    await navigateTo('/dashboard')
  } catch (e: any) {
    genStep.value = ''
    msg.error(formatError(e, '创建失败'))
  } finally { creating.value = false }
}

// 书脊配色
const spines = [['#4D8088','#3A6268'],['#D49A4E','#B07A2E'],['#884d5c','#6B3A47'],['#52A569','#3E7D50']]
function spineStyle(i: number) { const [a,b] = spines[i % spines.length]; return { background: `linear-gradient(180deg, ${a}, ${b})` } }
function enterProject(p: any) { selectProject(p.id, { id: p.id, title: p.title, genre: p.genre }); navigateTo('/dashboard') }
function progress(p: any) { const t = p.target_word_count || 200000; return Math.min(100, Math.round(((p.current_word_count||0)/t)*100)) }
</script>

<template>
  <div class="bookshelf-page">
    <div class="shelf-banner">
      <div class="shelf-banner-deco"></div>
      <div class="shelf-banner-text"><h1>我的书架</h1><p>{{ projects?.length || 0 }} 部作品</p></div>
      <div class="shelf-banner-actions">
        <label class="import-btn"><input type="file" accept=".json" style="display:none" @change="onImportFile" />导入</label>
        <a-button ghost @click="showCreate = true" style="color:#fff;border-color:rgba(255,255,255,0.5);">+ 新建小说</a-button>
        <NuxtLink to="/inspire"><a-button ghost style="color:#fff;border-color:rgba(255,255,255,0.5);">灵感模式</a-button></NuxtLink>
      </div>
    </div>

    <a-alert
      v-if="aiConfigured === false"
      type="warning" show-icon banner
      message="未配置 AI 模型，所有 AI 功能（生成章节/大纲/角色等）将无法使用。"
    >
      <template #action>
        <NuxtLink to="/ai-settings"><a-button size="small" type="primary">前往配置</a-button></NuxtLink>
      </template>
    </a-alert>

    <div class="book-grid-bg">
      <div v-if="projects && projects.length" style="display:flex;gap:8px;margin-bottom:16px;justify-content:center">
        <a-button size="small" :type="filterMode === 'all' ? 'primary' : 'default'" @click="filterMode = 'all'">全部</a-button>
        <a-button size="small" :type="filterMode === 'one_to_one' ? 'primary' : 'default'" @click="filterMode = 'one_to_one'">传统模式 (1→1)</a-button>
        <a-button size="small" :type="filterMode === 'one_to_many' ? 'primary' : 'default'" @click="filterMode = 'one_to_many'">细化模式 (1→N)</a-button>
      </div>
      <div v-if="filteredProjects && filteredProjects.length" class="book-grid">
        <div v-for="(p, i) in filteredProjects" :key="p.id" class="book-card" @click="enterProject(p)">
          <div class="book-spine" :style="spineStyle(i)"></div>
          <div class="book-page">
            <div class="book-title">{{ p.title }}</div>
            <div class="book-tags">
              <span class="book-tag">{{ p.genre || '其他' }}</span>
              <span class="book-tag" :style="{background: (p.outline_mode || 'one_to_one') === 'one_to_many' ? '#D9F0E5' : '#E8EEF4', color: (p.outline_mode || 'one_to_one') === 'one_to_many' ? '#1A7A42' : '#6B7D8E'}">
                {{ (p.outline_mode || 'one_to_one') === 'one_to_many' ? '1→N' : '1→1' }}
              </span>
            </div>
            <div class="book-desc">{{ p.synopsis || '暂无简介' }}</div>
            <div class="book-progress">
              <div class="progress-bar"><div class="progress-fill" :style="{width:progress(p)+'%'}"></div></div>
              <span class="progress-text">{{ progress(p) }}%</span>
            </div>
            <div class="book-stats"><span>{{ p.chapter_count || 0 }} 章</span><span class="book-words">{{ (p.current_word_count||0).toLocaleString() }} 字</span></div>
            <!-- 悬停操作 -->
            <div class="book-actions">
              <a-dropdown :trigger="['click']">
                <span @click="(e) => e.stopPropagation()" title="导出">⬇</span>
                <template #overlay>
                  <a-menu @click="(info: any) => onExport(p, info.key)">
                    <a-menu-item key="json">📦 全量 JSON（含设定/记忆/分析）</a-menu-item>
                    <a-menu-item key="txt">📄 整书 TXT（纯正文）</a-menu-item>
                  </a-menu>
                </template>
              </a-dropdown>
              <span @click="(e) => onDelete(p, e)" title="删除" class="del">✕</span>
            </div>
          </div>
        </div>
        <div class="book-card book-new" @click="showCreate = true">
          <div class="book-new-inner"><div style="font-size:36px;">✍️</div><div style="font-size:15px;font-weight:600;color:#D49A4E;">新建小说</div></div>
        </div>
      </div>
      <div v-else class="empty-state">
        <div style="font-size:56px;margin-bottom:16px;">📚</div>
        <p style="font-size:16px;color:#595959;margin-bottom:20px;">还没有作品</p>
        <div style="display:flex;gap:12px;justify-content:center;">
          <a-button type="primary" size="large" @click="showCreate = true">✍️ 创建作品</a-button>
          <NuxtLink to="/inspire"><a-button size="large">💡 灵感模式</a-button></NuxtLink>
        </div>
      </div>
    </div>
  </div>

  <!-- 新建向导 -->
  <a-modal v-model:open="showCreate" title="创建新项目" width="560px" :mask-closable="false" :footer="null">
    <a-alert v-if="!creating" message="填写基本信息后，AI 将自动为您生成世界观、角色和大纲节点（大纲可在项目内手动展开为章节）" type="info" show-icon style="margin-bottom:16px" />
    <div v-if="creating" class="creating-state">
      <a-spin size="large" />
      <p style="margin-top:16px;color:#4D8088;">{{ genStep || '正在创建...' }}</p>
      <p style="font-size:12px;color:#999;">请稍候，AI 正在生成内容</p>
    </div>
    <a-form v-else layout="vertical">
      <a-form-item label="书名" required><a-input v-model:value="wizard.title" placeholder="请输入书名" /></a-form-item>
      <a-form-item label="小说简介"><a-textarea v-model:value="wizard.synopsis" :rows="2" :maxlength="300" show-count placeholder="一句话描述故事" /></a-form-item>
      <a-form-item label="主题"><a-textarea v-model:value="wizard.theme" :rows="2" :maxlength="500" show-count placeholder="故事的核心主题（如：复仇与救赎）" /></a-form-item>
      <a-row :gutter="12">
        <a-col :span="8"><a-form-item label="类型"><a-auto-complete v-model:value="wizard.genre" :options="genres.map(g => ({ value: g }))" :filter-option="(input:string, option:any) => option.value.toLowerCase().includes(input.toLowerCase())" allow-clear placeholder="选择或输入类型" /></a-form-item></a-col>
        <a-col :span="8"><a-form-item label="叙事视角"><a-select v-model:value="wizard.narrative_pov" style="width:100%"><a-select-option label="第三人称" value="第三人称" /><a-select-option label="第一人称" value="第一人称" /><a-select-option label="全知视角" value="全知视角" /></a-select></a-form-item></a-col>
        <a-col :span="8"><a-form-item label="主角名字（可选）"><a-input v-model:value="wizard.protagonist_name" placeholder="留空则AI生成" /></a-form-item></a-col>
      </a-row>
      <a-form-item label="大纲章节模式">
        <div class="mode-cards">
          <div class="mode-card" :class="{ active: wizard.outline_mode === 'one_to_one' }" @click="wizard.outline_mode = 'one_to_one'">
            <div class="mode-card-title">📖 传统模式 (1→1)</div>
            <div class="mode-card-desc">一个大纲对应一个章节</div>
            <div class="mode-card-hint">💡 适合：简单剧情、快速创作、短篇</div>
          </div>
          <div class="mode-card" :class="{ active: wizard.outline_mode === 'one_to_many' }" @click="wizard.outline_mode = 'one_to_many'">
            <div class="mode-card-title">📚 细化模式 (1→N) <a-tag color="green" size="small">推荐</a-tag></div>
            <div class="mode-card-desc">一个大纲可展开为多个章节</div>
            <div class="mode-card-hint">💡 适合：复杂剧情、长篇创作、细化控制</div>
          </div>
        </div>
        <div style="font-size:12px;color:#999;margin-top:4px;">⚠️ 创建后不可更改，请根据创作习惯选择</div>
      </a-form-item>
      <a-row :gutter="12">
        <a-col :span="12"><a-form-item label="角色数量"><a-input-number v-model:value="wizard.character_count" :min="2" :max="15" /> 个</a-form-item></a-col>
        <a-col :span="12"><a-form-item label="初始大纲"><a-radio-group v-model:value="wizard.chapter_count">
          <a-radio-button :value="3">3 章</a-radio-button>
          <a-radio-button :value="5">5 章</a-radio-button>
          <a-radio-button :value="10">10 章</a-radio-button>
        </a-radio-group></a-form-item></a-col>
        <a-col :span="12"><a-form-item label="目标字数"><a-input-number v-model:value="wizard.target_word_count" :min="10000" :max="5000000" :step="10000" /> 字</a-form-item></a-col>
      </a-row>
      <div style="text-align:right;margin-top:8px;">
        <a-button @click="showCreate = false">取消</a-button>
        <a-button type="primary" @click="onCreate" style="margin-left:8px;">🚀 创建并 AI 生成</a-button>
      </div>
    </a-form>
  </a-modal>

  <!-- 导入确认 -->
  <a-modal v-model:open="showImport" title="导入项目" width="500px">
    <p style="color:#666;margin-bottom:12px;">将从 JSON 文件导入为新项目（原标题后加"（导入）"）：</p>
    <a-textarea :value="importText.slice(0, 500) + '...'" :rows="5" readonly />
    <template #footer><a-button @click="showImport = false">取消</a-button><a-button type="primary" @click="onImport">确认导入</a-button></template>
  </a-modal>
</template>

<style scoped>
.shelf-banner { background: linear-gradient(135deg, #4D8088 0%, #5A9098 100%); border-radius:18px; padding:32px; color:#fff; display:flex; align-items:center; gap:20px; margin-bottom:28px; position:relative; overflow:hidden; }
.shelf-banner-deco { position:absolute; right:-30px; top:-30px; width:160px; height:160px; border-radius:50%; background:rgba(255,255,255,0.1); }
.shelf-banner-text { flex:1; z-index:1; }
.shelf-banner-text h1 { font-size:26px; margin-bottom:6px; font-family:Georgia,'Noto Serif SC',serif; }
.shelf-banner-text p { font-size:13px; opacity:0.9; }
.shelf-banner-actions { display:flex; gap:10px; z-index:1; align-items:center; }
.import-btn { color:#fff; border:1px solid rgba(255,255,255,0.5); border-radius:6px; padding:4px 15px; cursor:pointer; font-size:14px; height:32px; display:inline-flex; align-items:center; }
.import-btn:hover { background:rgba(255,255,255,0.1); }
.book-grid-bg { background-image: radial-gradient(rgba(43,43,43,0.08) 1px, transparent 0); background-size:18px 18px; padding:8px; border-radius:16px; }
.book-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:20px; }
.book-card { display:flex; height:300px; border-radius:4px 12px 12px 4px; overflow:hidden; cursor:pointer; background:#fff; border:1px solid rgba(43,43,43,0.18); box-shadow:0 10px 22px -12px rgba(43,43,43,0.28); transition:all .25s; position:relative; }
.book-card:hover { transform:translateY(-8px) rotateX(2deg); box-shadow:0 16px 32px -12px rgba(43,43,43,0.35); }
.book-spine { width:22px; flex-shrink:0; box-shadow:inset -3px 0 6px rgba(0,0,0,0.25); }
.book-page { flex:1; padding:24px 20px; display:flex; flex-direction:column; min-width:0; }
.book-title { font-size:22px; font-weight:700; color:#2B2B2B; margin-bottom:10px; font-family:Georgia,'Noto Serif SC',serif; line-height:1.3; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.book-tags { display:flex; gap:6px; margin-bottom:10px; }
.book-tag { font-size:11px; padding:2px 8px; border-radius:4px; background:#EAF0F1; color:#4D8088; }
.book-desc { font-size:13px; color:#8C8C8C; line-height:1.6; flex:1; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }
.book-progress { display:flex; align-items:center; gap:8px; margin:10px 0 6px; }
.progress-bar { flex:1; height:6px; background:#F0EDE6; border-radius:999; overflow:hidden; }
.progress-fill { height:100%; background:linear-gradient(90deg,#4D8088,#6B9CA4); border-radius:999; }
.progress-text { font-size:11px; color:#8C8C8C; font-family:Georgia,serif; }
.book-stats { display:flex; justify-content:space-between; font-size:11px; color:#8C8C8C; }
.book-words { font-family:Georgia,serif; }
.book-actions { position:absolute; top:10px; right:10px; display:none; gap:8px; background:rgba(255,255,255,0.9); border-radius:6px; padding:4px 8px; }
.book-card:hover .book-actions { display:flex; }
.book-actions span { cursor:pointer; font-size:14px; color:#595959; padding:2px 4px; }
.book-actions span:hover { color:#4D8088; }
.book-actions .del:hover { color:#C75B5B; }
.book-new { background:linear-gradient(135deg,rgba(212,154,78,0.08),rgba(212,154,78,0.02)); border:2px dashed rgba(212,154,78,0.4); align-items:center; justify-content:center; }
.book-new:hover { border-color:#D49A4E; }
.book-new-inner { text-align:center; }
.empty-state { text-align:center; padding:80px 20px; }
.creating-state { text-align:center; padding:40px 0; }
.mode-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 4px; }
.mode-card { border: 2px solid #E8E4DC; border-radius: 8px; padding: 14px; cursor: pointer; transition: all .2s; background: #FAFAF7; }
.mode-card:hover { border-color: #B5C7CB; }
.mode-card.active { border-color: #4D8088; background: #EAF0F1; }
.mode-card-title { font-size: 14px; font-weight: 600; color: #2B2B2B; margin-bottom: 6px; display:flex; align-items:center; gap:6px; }
.mode-card-desc { font-size: 13px; color: #595959; margin-bottom: 8px; }
.mode-card-hint { font-size: 12px; color: #8C8C8C; }
</style>
