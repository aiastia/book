<script setup lang="ts">
// 仪表盘：当前项目的统计 + 快捷操作
// 基于后端项目级接口
import { useBookApi } from '~/composables/useBookApi'
import { useProject } from '~/composables/useProject'

useHead({ title: '仪表盘 — 墨语' })

const { currentProjectId, currentProjectInfo, syncFromQuery, projectUrl } = useProject()
syncFromQuery()

const api = useBookApi()

// 重定向：如果没有选择项目，跳到书架
if (!currentProjectId.value) {
  await navigateTo('/books')
}

// 检查 AI 模型是否已配置（延迟重试，避免 auth 未就绪）
const aiConfigured = ref<boolean | null>(null)
async function checkAiConfig() {
  try {
    const models = await api.listAiModels()
    aiConfigured.value = Array.isArray(models) && models.length > 0
  } catch {
    // auth 可能未就绪，2秒后重试一次
    if (aiConfigured.value === null) {
      setTimeout(async () => {
        try {
          const models2 = await api.listAiModels()
          aiConfigured.value = Array.isArray(models2) && models2.length > 0
        } catch { aiConfigured.value = true /* 失败不报，静默跳过 */ }
      }, 2000)
    }
  }
}
checkAiConfig()

const { data: project } = await useFetch(() => `/api/projects/${currentProjectId.value}`)
const { data: chapters } = await useFetch(() => `/api/projects/${currentProjectId.value}/chapters`)
const { data: characters } = await useFetch(() => `/api/projects/${currentProjectId.value}/characters`)
const { data: outlines } = await useFetch(() => `/api/projects/${currentProjectId.value}/outlines`)

const stats = computed(() => {
  const wordCount = chapters.value?.reduce((sum: number, c: any) => sum + (c.word_count || 0), 0) ?? 0
  return {
    chapters: chapters.value?.length ?? 0,
    words: wordCount.toLocaleString(),
    characters: characters.value?.length ?? 0,
    outlines: outlines.value?.length ?? 0,
  }
})

const cards = computed(() => [
  { label: '章节', value: stats.value.chapters, icon: '📄', suffix: '' },
  { label: '总字数', value: stats.value.words, icon: '✏️', suffix: '' },
  { label: '角色', value: stats.value.characters, icon: '👥', suffix: '' },
  { label: '大纲', value: stats.value.outlines, icon: '📋', suffix: '' },
])

const chapterStatusText: Record<string, string> = { draft: '草稿', generating: '创作中', completed: '已完成' }
const recentChapters = computed(() =>
  (chapters.value || []).slice(0, 5).map((c: any) => ({
    title: `第 ${c.chapter_number} 章 · ${c.title || '无标题'}`,
    meta: `${c.word_count || 0} 字`,
    badge: chapterStatusText[c.status] || c.status || '草稿',
    type: c.status === 'completed' ? 'success' : 'warning',
  })),
)

const quickActions = computed(() => [
  { icon: '📋', label: '故事大纲', to: projectUrl('/outline') },
  { icon: '📝', label: '章节创作', to: projectUrl('/chapters') },
  { icon: '👤', label: '角色管理', to: projectUrl('/characters') },
  { icon: '🌍', label: '世界设定', to: projectUrl('/worldview') },
  { icon: '🔮', label: '伏笔管理', to: projectUrl('/foreshadows') },
  { icon: '📊', label: '剧情分析', to: projectUrl('/analysis') },
  { icon: '⚙️', label: 'AI 设置', to: '/ai-settings' },
])

// 封面提示词
const msg = useMessage()
const coverLoading = ref(false)
const coverPrompt = ref('')
const showCover = ref(false)
const imageLoading = ref(false)
const imageConfigured = ref(false)

async function checkImageConfig() {
  try {
    const models = await api.listAiModels()
    const def = models.find((m: any) => m.is_default) || models[0]
    imageConfigured.value = !!(def?.image_base_url && def?.image_api_key && def?.image_model)
  } catch (_) { /* ignore */ }
}
checkImageConfig()

async function onGenerateCover() {
  coverLoading.value = true
  try {
    const res = await api.generateCoverPrompt()
    coverPrompt.value = typeof res.cover_prompt === 'string' ? res.cover_prompt : JSON.stringify(res.cover_prompt, null, 2)
    showCover.value = true
  } catch (e: any) {
    msg.error('生成失败：' + formatError(e))
  } finally {
    coverLoading.value = false
  }
}

async function onGenerateImage() {
  if (!coverPrompt.value) { msg.warning('请先生成提示词'); return }
  imageLoading.value = true
  try {
    const res = await api.generateCoverImage(coverPrompt.value)
    msg.success('封面已生成')
    showCover.value = false
    if (project.value) project.value.cover_url = res.cover_url
  } catch (e: any) {
    msg.error('出图失败：' + formatError(e))
  } finally { imageLoading.value = false }
}

function copyCoverPrompt() {
  navigator.clipboard.writeText(coverPrompt.value)
  msg.success('已复制到剪贴板')
}
</script>

<template>
  <PageHeader :title="currentProjectInfo?.title || project?.title || '加载中…'">
    <template #actions>
      <a-button :loading="coverLoading" @click="onGenerateCover">{{ coverLoading ? '生成中…' : '🖼 封面提示词' }}</a-button>
      <NuxtLink to="/books"><a-button>切换书籍</a-button></NuxtLink>
    </template>
  </PageHeader>

  <div class="page-content">
    <div class="stats-grid">
      <a-card v-for="s in cards" :key="s.label" hoverable class="stat-card">
        <div class="stat-card-header">
          <span class="stat-card-label">{{ s.label }}</span>
          <span class="stat-card-icon">{{ s.icon }}</span>
        </div>
        <a-statistic :value="s.value" />
      </a-card>
    </div>

    <!-- AI 模型未配置提示 -->
    <a-alert
      v-if="aiConfigured === false"
      type="warning" show-icon style="margin-bottom:16px;"
      message="未配置 AI 模型"
      description="请先在 AI 设置中配置至少一个 AI 模型（API 地址 + 密钥 + 模型名），否则所有 AI 功能（生成章节/大纲/角色等）将无法使用。"
    >
      <template #action>
        <NuxtLink to="/ai-settings"><a-button size="small" type="primary">前往配置</a-button></NuxtLink>
      </template>
    </a-alert>

    <!-- 创作引导：当项目还是空的时候展示 -->
    <a-card v-if="stats.chapters === 0 && stats.outlines === 0" class="guide-card">
      <h3 style="font-size:16px;font-weight:600;margin-bottom:16px;color:#4D8088;">🚀 开始你的创作之旅</h3>
      <p style="color:#666;margin-bottom:20px;">按照以下步骤，AI 帮你从零构建一部完整小说</p>
      <div class="guide-steps">
        <NuxtLink :to="projectUrl('/worldview')" class="guide-step">
          <div class="guide-step-num">1</div>
          <div class="guide-step-body">
            <div class="guide-step-title">🌍 构建世界观</div>
            <div class="guide-step-desc">设定故事背景、力量体系</div>
          </div>
        </NuxtLink>
        <NuxtLink :to="projectUrl('/characters')" class="guide-step">
          <div class="guide-step-num">2</div>
          <div class="guide-step-body">
            <div class="guide-step-title">👥 创建角色</div>
            <div class="guide-step-desc">设定主角、配角的人物卡片</div>
          </div>
        </NuxtLink>
        <NuxtLink :to="projectUrl('/outline')" class="guide-step">
          <div class="guide-step-num">3</div>
          <div class="guide-step-body">
            <div class="guide-step-title">📋 生成大纲</div>
            <div class="guide-step-desc">AI 基于世界观和角色自动生成</div>
          </div>
        </NuxtLink>
        <NuxtLink :to="projectUrl('/chapters')" class="guide-step">
          <div class="guide-step-num">4</div>
          <div class="guide-step-body">
            <div class="guide-step-title">📝 写章节</div>
            <div class="guide-step-desc">AI 根据大纲逐章生成正文</div>
          </div>
        </NuxtLink>
      </div>
    </a-card>

    <h3 class="section-title">快捷操作</h3>
    <div class="quick-actions">
      <NuxtLink v-for="a in quickActions" :key="a.to" :to="a.to" class="quick-action">
        <div class="quick-action-icon">{{ a.icon }}</div>
        <span class="quick-action-label">{{ a.label }}</span>
      </NuxtLink>
    </div>

    <a-card class="recent-panel">
      <template #title>
        <div class="recent-panel-header">
          <span>最近章节</span>
          <NuxtLink :to="projectUrl('/chapters')" class="recent-panel-more">查看全部 →</NuxtLink>
        </div>
      </template>
      <div v-if="recentChapters.length">
        <div v-for="(r, i) in recentChapters" :key="i" class="recent-item">
          <div class="recent-item-info">
            <div class="recent-item-title">{{ r.title }}</div>
            <div class="recent-item-meta">{{ r.meta }}</div>
          </div>
          <a-tag :color="r.type === 'success' ? 'success' : 'warning'" size="small">{{ r.badge }}</a-tag>
        </div>
      </div>
      <a-empty v-else description="暂无章节，先去生成大纲吧" :image-style="{ height: '60px' }" />
    </a-card>
  </div>

  <!-- 封面提示词弹窗 -->
  <a-modal v-model:open="showCover" title="小说封面提示词" width="600px">
    <p style="color:#666;margin-bottom:12px;">AI 根据你的小说信息生成的封面设计提示词，可用于 Midjourney、DALL-E 等图像生成工具</p>
    <div style="background:#f9f9f9;border:1px solid #e5e7eb;border-radius:8px;padding:16px;font-size:14px;line-height:1.8;white-space:pre-wrap;max-height:400px;overflow-y:auto;">{{ coverPrompt }}</div>
    <template #footer>
      <a-button @click="showCover = false">关闭</a-button>
      <a-button @click="copyCoverPrompt">复制提示词</a-button>
      <a-button v-if="imageConfigured" type="primary" :loading="imageLoading" @click="onGenerateImage">生成封面图片</a-button>
      <a-tooltip v-else title="请在 AI 设置中配置图像生成 API">
        <a-button type="primary" disabled>生成封面图片（未配置 API）</a-button>
      </a-tooltip>
    </template>
  </a-modal>
</template>

<style scoped>
.stats-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:20px; margin-bottom:32px; }
.stat-card { border-radius:10px; }
.stat-card-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; }
.stat-card-label { font-size:13px; color:#999; font-weight:500; }
.stat-card-icon { font-size:20px; }
.section-title { font-size:16px; font-weight:600; margin-bottom:16px; }
.guide-card { border-radius:12px; margin-bottom:24px; background:linear-gradient(135deg,#f0f7f0,#fafefa); border:1px solid #c8e6c9; }
.guide-steps { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:16px; }
.guide-step { display:flex; gap:12px; padding:16px; background:#fff; border:1px solid #e5e7eb; border-radius:10px; text-decoration:none; color:#333; transition:all .2s; }
.guide-step:hover { border-color:#4D8088; box-shadow:0 2px 8px rgba(46,125,50,.1); transform:translateY(-2px); }
.guide-step-num { width:28px; height:28px; border-radius:50%; background:#4D8088; color:#fff; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:14px; flex-shrink:0; }
.guide-step-title { font-size:14px; font-weight:600; margin-bottom:4px; }
.guide-step-desc { font-size:12px; color:#888; }
.quick-actions { display:grid; grid-template-columns:repeat(auto-fill,minmax(140px,1fr)); gap:16px; margin-bottom:32px; }
.quick-action { display:flex; flex-direction:column; align-items:center; gap:10px; padding:20px 12px; background:#fff; border:1px solid #e5e7eb; border-radius:10px; text-decoration:none; color:#333; transition:all .2s; }
.quick-action:hover { border-color:#4D8088; box-shadow:0 2px 8px rgba(46,125,50,.1); transform:translateY(-1px); }
.quick-action-icon { width:40px; height:40px; border-radius:10px; background:#EAF0F1; display:flex; align-items:center; justify-content:center; font-size:18px; }
.quick-action-label { font-size:13px; font-weight:500; }
.recent-panel { border-radius:10px; }
.recent-panel-header { display:flex; align-items:center; justify-content:space-between; width:100%; font-size:15px; font-weight:600; }
.recent-panel-more { font-size:13px; color:#4D8088; text-decoration:none; }
.recent-item { display:flex; align-items:center; justify-content:space-between; padding:14px 20px; border-bottom:1px solid #f5f5f5; }
.recent-item:last-child { border-bottom:none; }
.recent-item-info { flex:1; min-width:0; }
.recent-item-title { font-size:14px; font-weight:500; margin-bottom:2px; }
.recent-item-meta { font-size:12px; color:#999; }
@media (max-width:1024px) { .stats-grid{grid-template-columns:repeat(2,1fr);} }
@media (max-width:768px) { .stats-grid{grid-template-columns:1fr;} }
</style>
