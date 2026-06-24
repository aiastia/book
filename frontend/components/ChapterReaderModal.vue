<script setup lang="ts">
/**
 * 沉浸式章节阅读器（对标 MuMuAINovel components/ChapterReader.tsx）
 * 纯正文阅读，无标注、无分析侧栏。支持主题/字号/行高调节，键盘翻页。
 */
import { apiGet } from '~/composables/useApi'

const props = defineProps<{
  visible: boolean
  chapter: any | null
  chapters: any[]
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'change', chapterId: number): void
}>()

const msg = useMessage()
const loading = ref(false)

// 合并外部 loading
const isBusy = computed(() => props.loading || loading.value)

// ===== 阅读设置（持久化 localStorage） =====
interface ReaderSettings {
  fontSize: number
  theme: 'light' | 'sepia' | 'dark'
  lineHeight: number
}
const SETTINGS_KEY = 'moyu_reader_settings'
function loadSettings(): ReaderSettings {
  try {
    const s = localStorage.getItem(SETTINGS_KEY)
    if (s) return JSON.parse(s)
  } catch {}
  return { fontSize: 18, theme: 'light', lineHeight: 1.8 }
}
function saveSettings(s: ReaderSettings) {
  try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(s)) } catch {}
}
const settings = reactive<ReaderSettings>(loadSettings())
watch(settings, () => saveSettings({ ...settings }), { deep: true })

// ===== 主题配色 =====
const themeStyles = computed(() => {
  switch (settings.theme) {
    case 'light':
      return { bg: '#fff', text: '#2B2B2B', headerBg: '#FAFAF7', border: '#E8E4DC' }
    case 'sepia':
      return { bg: '#F5F0E8', text: '#4A3F35', headerBg: '#EDE6D8', border: '#D4C8B0' }
    case 'dark':
      return { bg: '#1A1A1A', text: '#D4D4D4', headerBg: '#222', border: '#333' }
  }
})

const showSettings = ref(false)
const isMobile = ref(false)
function updateMobile() {
  isMobile.value = typeof window !== 'undefined' && window.innerWidth <= 768
}
onMounted(() => { updateMobile(); window.addEventListener('resize', updateMobile) })
onUnmounted(() => window.removeEventListener('resize', updateMobile))

// ===== 导航 =====
const navInfo = computed(() => {
  if (!props.chapter || !props.chapters?.length) return { prev: null, next: null }
  const list = props.chapters
  const idx = list.findIndex((c: any) => c.id === props.chapter.id)
  return {
    prev: idx > 0 ? list[idx - 1] : null,
    next: idx < list.length - 1 ? list[idx + 1] : null,
  }
})

function goPrev() {
  if (navInfo.value.prev) {
    loading.value = true
    emit('change', navInfo.value.prev.id)
  }
}
function goNext() {
  if (navInfo.value.next) {
    loading.value = true
    emit('change', navInfo.value.next.id)
  }
}

// 章节切换后恢复 loading
watch(() => props.chapter?.id, () => {
  loading.value = false
  // 回到顶部
  nextTick(() => {
    const el = document.querySelector('.reader-scroll-area')
    if (el) el.scrollTop = 0
  })
})

// ===== 键盘快捷键 =====
function onKeydown(e: KeyboardEvent) {
  if (!props.visible) return
  if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
  if (e.key === 'ArrowLeft') goPrev()
  else if (e.key === 'ArrowRight') goNext()
  else if (e.key === 'Escape') emit('close')
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

// ===== 设置 =====
function setFontSize(v: number) { settings.fontSize = v }
function setLineHeight(v: number) { settings.lineHeight = v }
function setTheme(v: 'light' | 'sepia' | 'dark') { settings.theme = v }
</script>

<template>
  <a-modal
    :open="visible"
    :footer="null"
    :closable="false"
    :mask-closable="false"
    width="100%"
    :wrap-class-name="'reader-fullscreen-modal'"
  >
    <div class="reader-modal-root" :style="{ background: themeStyles.bg, color: themeStyles.text }">
      <!-- 顶部工具栏 -->
      <div class="reader-header" :style="{ background: themeStyles.headerBg, borderColor: themeStyles.border }">
        <a-button type="text" @click="$emit('close')" :style="{ color: themeStyles.text }">
          ✕ {{ isMobile ? '' : '关闭' }}
        </a-button>
        <span class="reader-title">
          第{{ chapter?.chapter_number }}章 · {{ chapter?.title }}
        </span>
        <a-button
          :type="showSettings ? 'primary' : 'text'"
          @click="showSettings = !showSettings"
          :style="{ color: showSettings ? undefined : themeStyles.text }"
          title="阅读设置"
        >
          ⚙
        </a-button>
      </div>

      <!-- 设置面板 -->
      <div v-if="showSettings" class="reader-settings" :style="{ background: themeStyles.headerBg, borderColor: themeStyles.border }">
        <div class="settings-row">
          <span class="settings-label">字号 {{ settings.fontSize }}px</span>
          <input
            type="range" min="14" max="28" :value="settings.fontSize"
            @input="(e: any) => setFontSize(Number(e.target.value))"
            class="settings-slider"
          />
        </div>
        <div class="settings-row">
          <span class="settings-label">行高 {{ settings.lineHeight }}</span>
          <input
            type="range" min="1.4" max="2.5" step="0.1" :value="settings.lineHeight"
            @input="(e: any) => setLineHeight(Number(e.target.value))"
            class="settings-slider"
          />
        </div>
        <div class="settings-row">
          <span class="settings-label">主题</span>
          <a-radio-group :value="settings.theme" @change="(e: any) => setTheme(e.target.value)" size="small">
            <a-radio-button value="light">日间</a-radio-button>
            <a-radio-button value="sepia">护眼</a-radio-button>
            <a-radio-button value="dark">夜间</a-radio-button>
          </a-radio-group>
        </div>
      </div>

      <!-- 正文区域 -->
      <div class="reader-scroll-area">
        <a-spin :spinning="isBusy" tip="加载中…">
          <div class="reader-body" :style="{
            fontSize: settings.fontSize + 'px',
            lineHeight: settings.lineHeight,
            color: themeStyles.text,
            padding: isMobile ? '24px 16px 40px' : '40px 60px 40px',
          }">
            <template v-if="chapter?.content">
              <p
                v-for="(para, i) in chapter.content.split('\n').filter((p: string) => p.trim())"
                :key="i"
                class="reader-para"
              >{{ para }}</p>
            </template>
            <div v-else-if="isBusy" class="reader-empty">加载中…</div>
            <div v-else class="reader-empty">暂无内容</div>
          </div>
        </a-spin>
      </div>

      <!-- 底部导航 -->
      <div class="reader-footer" :style="{ background: themeStyles.headerBg, borderColor: themeStyles.border }">
        <a-button
          type="primary" :disabled="!navInfo.prev || isBusy"
          @click="goPrev" :size="isMobile ? 'middle' : 'large'"
        >← {{ isMobile ? '' : '上一章' }}</a-button>
        <div class="footer-center">
          <div>{{ chapter?.word_count || 0 }} 字</div>
          <div v-if="navInfo" class="footer-hint">
            {{ navInfo.prev ? `← ${navInfo.prev.title}` : '已是第一章' }}
            &nbsp;|&nbsp;
            {{ navInfo.next ? `${navInfo.next.title} →` : '已是最后一章' }}
          </div>
        </div>
        <a-button
          type="primary" :disabled="!navInfo.next || isBusy"
          @click="goNext" :size="isMobile ? 'middle' : 'large'"
        >{{ isMobile ? '' : '下一章' }} →</a-button>
      </div>
    </div>
  </a-modal>
</template>

<style>
/* 全局：全屏 Modal 覆盖 */
.reader-fullscreen-modal {
  position: fixed !important;
  inset: 0 !important;
}
.reader-fullscreen-modal .ant-modal {
  max-width: 100vw !important;
  width: 100% !important;
  top: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  height: 100vh !important;
  overflow: hidden !important;
}
.reader-fullscreen-modal .ant-modal-content {
  height: 100vh;
  border-radius: 0;
  box-shadow: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.reader-fullscreen-modal .ant-modal-body {
  flex: 1;
  padding: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
</style>

<style scoped>
.reader-modal-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.reader-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  border-bottom: 1px solid;
  flex-shrink: 0;
  z-index: 10;
}
.reader-title {
  font-weight: 600;
  font-size: 15px;
  max-width: 60%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reader-settings {
  padding: 14px 20px;
  border-bottom: 1px solid;
  flex-shrink: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
}
.settings-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.settings-label {
  font-size: 13px;
  min-width: 80px;
}
.settings-slider {
  width: 140px;
  accent-color: #4D8088;
}

.reader-scroll-area {
  flex: 1;
  overflow-y: auto;
  scroll-behavior: smooth;
}
.reader-body {
  max-width: 1000px;
  margin: 0 auto;
  min-height: 100%;
  text-align: justify;
  word-break: break-word;
  overflow-wrap: break-word;
}
.reader-para {
  text-indent: 2em;
  margin: 0 0 0.8em 0;
}
.reader-empty {
  text-align: center;
  padding: 60px 20px;
  opacity: 0.5;
}

.reader-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  border-top: 1px solid;
  flex-shrink: 0;
}
.footer-center {
  text-align: center;
  font-size: 13px;
}
.footer-hint {
  font-size: 11px;
  opacity: 0.6;
  margin-top: 2px;
}

@media (max-width: 768px) {
  .reader-header { padding: 10px 12px; }
  .reader-settings { padding: 12px 16px; flex-direction: column; gap: 8px; }
  .reader-body { padding: 24px 16px 40px !important; }
  .reader-footer { padding: 12px 16px; }
  .reader-title { font-size: 14px; }
}
</style>
