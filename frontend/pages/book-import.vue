<script setup lang="ts">
import { useProjectApi } from '~/composables/useProjectApi'
import { UploadOutlined, LoadingOutlined } from '@ant-design/icons-vue'
useHead({ title: '拆书导入 — 墨语' })
const msg = useMessage()
const api = useProjectApi()
const { data: imported, refresh } = await useApi<any[]>('/api/imported-books', { key: 'imported-books' })
const uploading = ref(false)
const fileList = ref<any[]>([])

// 反向解析状态
const parseTarget = ref<any>(null)
const parseStep = ref(0) // 0=未开始, 1=提取项目信息, 2=确认创建, 3=生成大纲, 4=完成
const parseLoading = ref(false)
const parseResult = ref<any>(null)
const createdProjectId = ref<number | null>(null)
const outlineProgress = ref({ current: 0, total: 0 })

async function handleUpload(options: any) {
  const file = options.file
  if (!file) return
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', file)
    const config = useRuntimeConfig()
    const base = config.public.apiBase
    const token = localStorage.getItem('moyu_token')
    const resp = await $fetch(base + '/api/projects/book-import', {
      method: 'POST',
      body: formData,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    msg.success('导入成功！')
    await refresh()
  } catch (e: any) {
    msg.error('导入失败：' + formatError(e))
  } finally {
    uploading.value = false
  }
}

async function onDeleteImport(b: any) {
  if (!await msg.confirm('确认删除此导入记录？')) return
  try {
    await apiDelete(`/api/imported-books/${b.id}`)
    msg.success('已删除')
    await refresh()
  } catch { msg.error('删除失败') }
}

// 反向解析流程
function startParse(b: any) {
  parseTarget.value = b
  parseStep.value = 1
  parseResult.value = null
  createdProjectId.value = null
  outlineProgress.value = { current: 0, total: 0 }
  onExtractProjectInfo()
}

async function onExtractProjectInfo() {
  if (!parseTarget.value) return
  parseLoading.value = true
  try {
    // 模拟采样前3章文本（实际需要后端提供章节内容接口）
    const sampled = parseTarget.value.sampled_text || `书名：${parseTarget.value.title}，共${parseTarget.value.chapters || 0}章`
    const res = await api.bookImportSuggest({
      title: parseTarget.value.title,
      sampled_text: sampled,
    })
    parseResult.value = res
    parseStep.value = 2
  } catch (e: any) {
    msg.error('提取失败：' + formatError(e))
    parseStep.value = 0
  } finally {
    parseLoading.value = false
  }
}

async function onCreateProject() {
  if (!parseResult.value) return
  parseLoading.value = true
  try {
    const res = await api.createProject({
      title: parseResult.value.title || parseTarget.value.title,
      genre: parseResult.value.genre || '',
      synopsis: parseResult.value.description || parseResult.value.synopsis || '',
    })
    createdProjectId.value = res.id
    parseStep.value = 3
    msg.success('项目已创建，开始生成大纲')
    await onGenerateOutlines()
  } catch (e: any) {
    msg.error('创建失败：' + formatError(e))
  } finally {
    parseLoading.value = false
  }
}

async function onGenerateOutlines() {
  if (!createdProjectId.value || !parseTarget.value) return
  const totalChapters = parseTarget.value.chapters || 0
  if (totalChapters === 0) {
    parseStep.value = 4
    return
  }
  const batchSize = 5
  const totalBatches = Math.ceil(totalChapters / batchSize)
  outlineProgress.value = { current: 0, total: totalBatches }
  parseLoading.value = true

  try {
    for (let i = 0; i < totalBatches; i++) {
      const start = i * batchSize + 1
      const end = Math.min(start + batchSize - 1, totalChapters)
      // 使用导入的章节文本（实际需要从后端获取章节内容）
      const chaptersText = `第${start}-${end}章内容（来自导入的书籍）`
      await api.bookImportReverseOutlines({
        project_id: createdProjectId.value!,
        start_chapter: start,
        end_chapter: end,
        chapters_text: chaptersText,
      })
      outlineProgress.value.current = i + 1
    }
    parseStep.value = 4
    msg.success('大纲生成完成！')
  } catch (e: any) {
    msg.error('大纲生成失败：' + formatError(e))
  } finally {
    parseLoading.value = false
  }
}

function closeParse() {
  parseStep.value = 0
  parseTarget.value = null
  parseResult.value = null
}

// ===== #23 直接 TXT 导入（解析 + 批量落库，不走 AI）=====
const directMode = ref(false)
const directText = ref('')
const directParsing = ref(false)
const directResult = ref<{ chapters: any[]; stats: any } | null>(null)
const directTitle = ref('')
const directGenre = ref('')
const directImporting = ref(false)

async function onDirectParse() {
  if (!directText.value.trim()) { msg.warning('请粘贴小说文本'); return }
  directParsing.value = true
  directResult.value = null
  try {
    const r = await api.parseTxt({ text: directText.value })
    directResult.value = r
    if (r.chapters?.length) {
      msg.success(`解析成功：${r.chapters.length} 章`)
      if (!directTitle.value) directTitle.value = '导入小说'
    } else {
      msg.warning('未识别到章节，请检查文本格式')
    }
  } catch (e: any) { msg.error('解析失败：' + formatError(e)) }
  finally { directParsing.value = false }
}

async function onDirectImport() {
  if (!directResult.value?.chapters?.length) { msg.warning('请先解析'); return }
  if (!directTitle.value.trim()) { msg.warning('请输入书名'); return }
  directImporting.value = true
  try {
    const r = await api.fullImport({
      title: directTitle.value,
      genre: directGenre.value,
      chapters: directResult.value.chapters.map((c: any, i: number) => ({
        title: c.title || `第${i+1}章`,
        content: c.content || '',
        chapter_number: c.chapter_number || i + 1,
      })),
    })
    msg.success(`导入成功！${r.chapter_count} 章，共 ${r.total_words} 字`)
    // 跳转到项目
    await navigateTo(`/chapters?pid=${r.project_id}`)
  } catch (e: any) { msg.error('导入失败：' + formatError(e)) }
  finally { directImporting.value = false }
}

function onDirectUpload(file: any) {
  const reader = new FileReader()
  reader.onload = () => { directText.value = String(reader.result); onDirectParse() }
  reader.readAsText(file)
}
</script>

<template>
  <PageHeader title="拆书导入">
    <template #actions>
      <NuxtLink to="/books"><a-button>查看书架</a-button></NuxtLink>
    </template>
  </PageHeader>

  <div class="page-content">
    <!-- 模式切换 -->
    <div class="mode-tabs">
      <a-radio-group v-model:value="directMode" button-style="solid">
        <a-radio-button :value="false">🤖 AI 反向解析（提取设定+大纲）</a-radio-button>
        <a-radio-button :value="true">📄 直接导入（解析章节正文）</a-radio-button>
      </a-radio-group>
    </div>

    <!-- 直接 TXT 导入模式 -->
    <template v-if="directMode">
      <a-card title="📄 直接 TXT 导入" style="margin-bottom:16px">
        <a-alert message="粘贴或上传 TXT 小说文本，系统自动识别章节并导入为新项目（不走 AI，速度快）。" type="info" show-icon :closable="false" style="margin-bottom:12px" />
        <a-textarea v-model:value="directText" :rows="8" placeholder="粘贴小说全文（需含「第X章」等章节标记）..." />
        <div style="margin-top:10px;display:flex;gap:8px;align-items:center;">
          <a-button :loading="directParsing" :disabled="!directText.trim()" @click="onDirectParse">
            {{ directParsing ? '解析中…' : '🔍 解析章节' }}
          </a-button>
          <a-upload :show-file-list="false" :before-upload="onDirectUpload" accept=".txt">
            <a-button>📁 上传 TXT 文件</a-button>
          </a-upload>
        </div>
        <!-- 解析结果 -->
        <div v-if="directResult" class="parse-result">
          <a-divider />
          <div class="parse-stats">
            <a-tag color="blue">识别 {{ directResult.chapters.length }} 章</a-tag>
            <a-tag color="cyan">{{ directResult.stats.total_chars }} 字</a-tag>
            <a-tag v-if="directResult.stats.has_strong_titles" color="success">✓ 章节标记清晰</a-tag>
          </div>
          <!-- 章节预览 -->
          <div class="chap-preview">
            <div v-for="(c, i) in directResult.chapters.slice(0, 5)" :key="i" class="preview-item">
              <span class="preview-no">第{{ c.chapter_number }}章</span>
              <span class="preview-title">{{ c.title }}</span>
              <span class="preview-words">{{ c.content.length }} 字</span>
            </div>
            <div v-if="directResult.chapters.length > 5" class="preview-more">… 还有 {{ directResult.chapters.length - 5 }} 章</div>
          </div>
          <!-- 导入表单 -->
          <a-divider />
          <div class="import-form">
            <a-input v-model:value="directTitle" placeholder="书名" addon-before="书名" style="width:300px;margin-right:10px" />
            <a-input v-model:value="directGenre" placeholder="题材（可选）" addon-before="题材" style="width:200px;margin-right:10px" />
            <a-button type="primary" :loading="directImporting" :disabled="!directTitle.trim()" @click="onDirectImport">
              {{ directImporting ? '导入中…' : '导入为新项目' }}
            </a-button>
          </div>
        </div>
      </a-card>
    </template>

    <!-- AI 反向解析模式 -->
    <template v-else>
      <a-upload-dragger
        :auto-upload="true"
        :show-file-list="false"
        :custom-request="handleUpload"
        accept=".txt,.epub,.md,.markdown"
        class="upload-area"
      >
        <div class="upload-inner">
          <UploadOutlined style="font-size:48px;color:#c0c4cc;" />
          <div style="font-size:15px;color:#606266;margin-top:12px;">拖拽小说文件到此处，或点击选择</div>
          <div style="font-size:13px;color:#909399;margin-top:6px;">支持 TXT (GBK/UTF-8) / EPUB / Markdown</div>
        </div>
      </a-upload-dragger>

      <div v-if="uploading" style="text-align:center;padding:20px;">
        <LoadingOutlined :spin="true" style="font-size:24px;" />
        <span style="margin-left:8px;color:#888;">导入中...</span>
      </div>
    </template>

    <h3 style="font-size:15px;font-weight:600;margin:24px 0 12px;">已导入</h3>
    <div v-if="imported && imported.length">
      <a-card v-for="b in imported" :key="b.id" hoverable style="margin-bottom:10px;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <div>
            <div style="font-weight:500;">{{ b.title }}</div>
            <div style="font-size:12px;color:#888;margin-top:4px;">{{ b.chapters || 0 }} 章 · {{ b.updated || '' }}</div>
          </div>
          <div style="display:flex;align-items:center;gap:8px;">
            <a-tag :color="b.tag === '已完成' ? 'success' : 'default'" size="small">{{ b.tag || '导入' }}</a-tag>
            <a-button type="primary" size="small" @click="startParse(b)">智能解析</a-button>
            <a-button type="primary" size="small" danger @click="onDeleteImport(b)">删除</a-button>
          </div>
        </div>
      </a-card>
    </div>
    <a-empty v-else description="暂无导入记录" :image-style="{ height: '60px' }" />
  </div>

  <!-- 反向解析弹窗 -->
  <a-modal
    :open="parseStep > 0"
    title="智能解析 — 反向生成项目"
    width="600px"
    :footer="null"
    @cancel="closeParse"
  >
    <!-- 步骤1: 提取项目信息 -->
    <div v-if="parseStep === 1" style="text-align:center;padding:20px;">
      <LoadingOutlined :spin="true" style="font-size:24px;color:#4D8088;" />
      <p style="margin-top:12px;color:#666;">正在分析「{{ parseTarget?.title }}」提取项目信息…</p>
    </div>

    <!-- 步骤2: 确认项目信息 -->
    <div v-if="parseStep === 2 && parseResult">
      <h4 style="color:#4D8088;margin-bottom:12px;">提取的项目信息</h4>
      <a-descriptions bordered :column="1" size="small">
        <a-descriptions-item label="书名">{{ parseResult.title || parseTarget?.title }}</a-descriptions-item>
        <a-descriptions-item label="题材">{{ parseResult.genre || '-' }}</a-descriptions-item>
        <a-descriptions-item label="主题">{{ parseResult.theme || '-' }}</a-descriptions-item>
        <a-descriptions-item label="简介">{{ parseResult.description || parseResult.synopsis || '-' }}</a-descriptions-item>
        <a-descriptions-item label="叙事视角">{{ parseResult.narrative_perspective || parseResult.narrative_pov || '-' }}</a-descriptions-item>
        <a-descriptions-item label="目标字数">{{ parseResult.target_words || parseResult.target_word_count || '-' }}</a-descriptions-item>
      </a-descriptions>
      <div style="margin-top:16px;display:flex;justify-content:flex-end;gap:8px;">
        <a-button @click="closeParse">取消</a-button>
        <a-button type="primary" :loading="parseLoading" @click="onCreateProject">创建项目并生成大纲</a-button>
      </div>
    </div>

    <!-- 步骤3: 生成大纲中 -->
    <div v-if="parseStep === 3">
      <div style="text-align:center;padding:20px;">
        <LoadingOutlined :spin="true" style="font-size:24px;color:#4D8088;" />
        <p style="margin-top:12px;color:#666;">正在反向生成大纲…</p>
        <a-progress
          :percent="outlineProgress.total > 0 ? Math.round(outlineProgress.current / outlineProgress.total * 100) : 0"
          :format="() => `${outlineProgress.current}/${outlineProgress.total} 批`"
          style="max-width:300px;margin:12px auto;"
        />
      </div>
    </div>

    <!-- 步骤4: 完成 -->
    <div v-if="parseStep === 4" style="text-align:center;padding:20px;">
      <div style="font-size:48px;margin-bottom:12px;">✅</div>
      <h3 style="color:#4D8088;margin-bottom:8px;">解析完成！</h3>
      <p style="color:#666;">已创建项目并生成大纲，前往书架查看</p>
      <div style="margin-top:16px;display:flex;justify-content:center;gap:8px;">
        <NuxtLink v-if="createdProjectId" :to="`/outline?pid=${createdProjectId}`">
          <a-button type="primary">查看大纲</a-button>
        </NuxtLink>
        <a-button @click="closeParse">关闭</a-button>
      </div>
    </div>
  </a-modal>
</template>

<style scoped>
.mode-tabs { margin-bottom: 16px; }
.parse-result { margin-top: 12px; }
.parse-stats { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.chap-preview { background: #FAFAF7; border-radius: 6px; padding: 10px; }
.preview-item { display: flex; gap: 10px; padding: 6px 8px; border-bottom: 1px solid #F0EDE6; font-size: 13px; }
.preview-item:last-child { border-bottom: none; }
.preview-no { color: #4D8088; font-weight: 600; min-width: 60px; }
.preview-title { flex: 1; color: #2B2B2B; }
.preview-words { color: #8C8C8C; font-size: 12px; }
.preview-more { text-align: center; color: #8C8C8C; font-size: 12px; padding: 6px 0; }
.import-form { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.upload-area{width:100%;}
.upload-area :deep(.ant-upload-drag){width:100%;padding:48px 20px;border-radius:6px;}
.upload-inner{display:flex;flex-direction:column;align-items:center;}
</style>
