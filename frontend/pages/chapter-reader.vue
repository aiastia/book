<script setup lang="ts">
// 章节阅读器（#8）：带记忆标注的阅读视图
// 左侧章节正文（带高亮标注）+ 右侧标注侧边栏（按类型分组，点击定位）
import { useBookApi } from '~/composables/useBookApi'
import { useProject } from '~/composables/useProject'
import { apiGet } from '~/composables/useApi'
useHead({ title: '章节阅读 — 墨语' })
const { currentProjectId } = useProject()
if (!currentProjectId.value) await navigateTo('/books')
const api = useBookApi()
const msg = useMessage()
const route = useRoute()

const { data: chapters } = await api.getChapters()
const selectedId = ref<number | null>(null)
const chapter = ref<any>(null)
const annotations = ref<any[]>([])
const summary = ref<any>({})
const loading = ref(false)
const activeAnnotation = ref<any>(null)
const sidebarOpen = ref(false)  // 默认纯正文阅读（沉浸式），需要时手动开标注
const chapListOpen = ref(false) // 默认隐藏左侧章节列表，工具栏「目录」切出

// 从 query 选章节
onMounted(async () => {
  const qid = route.query.cid ? Number(route.query.cid) : null
  if (qid) await selectChapter(qid)
  else if (chapters.value?.length) await selectChapter(chapters.value[0].id)
})

async function selectChapter(id: number) {
  selectedId.value = id
  loading.value = true
  try {
    // 章节详情
    chapter.value = await apiGet<any>(`/api/projects/${currentProjectId.value}/chapters/${id}`)
    // 标注（有则展示高亮，无则纯正文阅读，不打扰）
    const r = await api.getAnnotations(id)
    annotations.value = r.annotations || []
    summary.value = r.summary || {}
  } catch (e: any) {
    msg.error('加载失败：' + formatError(e))
  } finally {
    loading.value = false
  }
}

// 键盘翻页（←/→）
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowLeft' && navInfo.value.prev) selectChapter(navInfo.value.prev.id)
  else if (e.key === 'ArrowRight' && navInfo.value.next) selectChapter(navInfo.value.next.id)
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

// 返回章节管理
function goBack() {
  navigateTo('/chapters')
}

// 字号控制
const fontSize = ref(16)
if (import.meta.client) {
  const saved = localStorage.getItem('moyu_reader_fontsize')
  if (saved) fontSize.value = Number(saved)
}
function changeFont(delta: number) {
  fontSize.value = Math.min(24, Math.max(12, fontSize.value + delta))
  if (import.meta.client) localStorage.setItem('moyu_reader_fontsize', String(fontSize.value))
}

// 标注按类型分组
const typeMeta: Record<string, { label: string; color: string; icon: string }> = {
  hook: { label: '剧情钩子', color: '#C75B5B', icon: '🎣' },
  foreshadow: { label: '伏笔', color: '#1677FF', icon: '🔮' },
  plot_point: { label: '关键情节', color: '#52A569', icon: '⭐' },
  character_event: { label: '角色事件', color: '#D49A4E', icon: '👤' },
}
const groupedAnnotations = computed(() => {
  const groups: Record<string, any[]> = { hook: [], foreshadow: [], plot_point: [], character_event: [] }
  for (const a of (annotations.value || [])) {
    if (a && a.type && groups[a.type]) groups[a.type].push(a)
  }
  return groups
})
// 预过滤的分组（只含有标注的类型，避免模板里 template v-if 包裹 v-for 导致 Codegen 错误）
const annotationGroups = computed(() => {
  return (Object.keys(typeMeta) as string[])
    .map(type => ({
      type,
      label: typeMeta[type].label,
      icon: typeMeta[type].icon,
      color: typeMeta[type].color,
      items: groupedAnnotations.value[type] || [],
    }))
    .filter(g => g.items.length > 0)
})

function onSelectAnnotation(ann: any) {
  activeAnnotation.value = ann
}

// 导航：前/后章
const navInfo = computed(() => {
  if (!chapters.value || !selectedId.value) return { prev: null, next: null }
  const list = chapters.value
  const idx = list.findIndex((c: any) => c.id === selectedId.value)
  return {
    prev: idx > 0 ? list[idx - 1] : null,
    next: idx < list.length - 1 ? list[idx + 1] : null,
  }
})
</script>

<template>
  <div class="reader-root">
    <ClientOnly>
      <div class="reader-page" :class="{ 'no-sidebars': !chapListOpen && !sidebarOpen, 'no-annot': !sidebarOpen }">
        <!-- 左侧章节列表（可切出） -->
        <div v-if="chapListOpen" class="chap-sidebar">
          <div class="chap-sidebar-title">章节列表</div>
          <div
            v-for="c in (chapters || [])" :key="c.id"
            class="chap-item" :class="{ active: selectedId === c.id }"
            @click="selectChapter(c.id)"
          >
            <span class="chap-num">第{{ c.chapter_number }}章</span>
            <span class="chap-title">{{ c.title }}</span>
          </div>
        </div>

        <!-- 中间正文 -->
        <div class="reader-main">
          <div class="reader-toolbar">
            <a-button size="small" @click="goBack">← 返回</a-button>
            <a-button size="small" @click="chapListOpen = !chapListOpen">📚 目录</a-button>
            <a-button size="small" :disabled="!navInfo.prev" @click="navInfo.prev && selectChapter(navInfo.prev.id)">上一章</a-button>
            <span v-if="chapter" class="toolbar-title">第 {{ chapter.chapter_number }} 章 · {{ chapter.title }}</span>
            <a-button size="small" :disabled="!navInfo.next" @click="navInfo.next && selectChapter(navInfo.next.id)">下一章 →</a-button>
            <a-button-group size="small">
              <a-button @click="changeFont(-1)">A-</a-button>
              <a-button @click="changeFont(1)">A+</a-button>
            </a-button-group>
            <a-button size="small" type="link" @click="sidebarOpen = !sidebarOpen">
              {{ sidebarOpen ? '隐藏标注' : '显示标注' }}
            </a-button>
          </div>
          <div v-if="chapter" class="reader-content" :style="{ fontSize: fontSize + 'px', lineHeight: 2 }">
            <AnnotatedText
              :content="chapter.content || ''"
              :annotations="annotations"
              :active-id="activeAnnotation ? `${activeAnnotation.type}-${activeAnnotation.position}` : null"
              @select="onSelectAnnotation"
            />
          </div>
          <div v-if="loading" style="text-align:center;padding:40px;color:#8C8C8C;">加载中…</div>
          <div v-else-if="!chapter" class="select-hint">请从左侧选择章节</div>
        </div>

        <!-- 右侧标注栏 -->
        <div v-if="sidebarOpen" class="annot-sidebar">
          <div class="annot-sidebar-title">
            <span>本章标注</span>
            <a-tag v-if="summary.total" color="blue">{{ summary.total }} 个</a-tag>
          </div>
          <!-- 统计 -->
          <div v-if="summary.total" class="annot-stats">
            <span v-for="group in annotationGroups" :key="'stat-'+group.type" class="stat-pill" :style="{ color: group.color }">
              {{ group.icon }} {{ group.items.length }}
            </span>
          </div>
          <!-- 分组标注 -->
          <div v-for="group in annotationGroups" :key="group.type" class="annot-group">
            <div class="group-title" :style="{ color: group.color }">{{ group.icon }} {{ group.label }}（{{ group.items.length }}）</div>
            <div
              v-for="(a, i) in group.items" :key="i"
              class="annot-item"
              :class="{ active: activeAnnotation === a }"
              :style="{ borderLeftColor: group.color }"
              @click="onSelectAnnotation(a)"
            >
              <div class="annot-item-title">{{ a.title }}</div>
              <div class="annot-item-content">{{ a.content }}</div>
            </div>
          </div>
          <div v-if="!summary.total" class="no-annot-hint">无标注</div>
          <div v-if="chapter && !summary.has_analysis" class="no-analysis-hint">
            此章节尚未分析 — 章节生成时会自动分析，标注来自分析结果。
          </div>
        </div>
      </div>

      <template #fallback>
        <div style="text-align:center;padding:60px;color:#8C8C8C;">加载阅读器…</div>
      </template>
    </ClientOnly>
  </div>
</template>

<style scoped>
.reader-page { display: grid; grid-template-columns: 200px 1fr 280px; gap: 16px; height: calc(100vh - 110px); }
/* 默认（无侧栏）：正文居中宽，沉浸式阅读 */
.reader-page.no-sidebars { grid-template-columns: 1fr; max-width: 820px; margin: 0 auto; width: 100%; }
.reader-page.no-sidebars .reader-content { max-width: none; }
/* 无标注栏（有目录） */
.reader-page.no-annot:not(.no-sidebars) { grid-template-columns: 200px 1fr; }
.chap-sidebar { background: #fff; border-radius: 8px; padding: 12px; overflow-y: auto; border: 1px solid #E8E4DC; }
.chap-sidebar-title { font-size: 13px; font-weight: 600; color: #4D8088; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid #F0EDE6; }
.chap-item { padding: 8px 10px; border-radius: 6px; cursor: pointer; margin-bottom: 4px; transition: background .15s; }
.chap-item:hover { background: #F8F6F1; }
.chap-item.active { background: #EAF0F1; color: #4D8088; font-weight: 600; }
.chap-num { font-size: 11px; color: #8C8C8C; display: block; }
.chap-title { font-size: 13px; }
.reader-main { display: flex; flex-direction: column; gap: 12px; overflow: hidden; }
.reader-toolbar { display: flex; align-items: center; gap: 8px; background: #fff; padding: 10px 14px; border-radius: 8px; border: 1px solid #E8E4DC; }
.toolbar-title { flex: 1; text-align: center; font-size: 14px; font-weight: 600; color: #2B2B2B; }
.reader-content { background: #fff; border-radius: 8px; padding: 32px 40px; overflow-y: auto; flex: 1; border: 1px solid #E8E4DC; box-shadow: inset 0 0 20px rgba(0,0,0,0.02); }
.annot-sidebar { background: #fff; border-radius: 8px; padding: 12px; overflow-y: auto; border: 1px solid #E8E4DC; }
.annot-sidebar-title { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; color: #4D8088; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid #F0EDE6; }
.annot-stats { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.stat-pill { font-size: 12px; background: #F8F6F1; padding: 2px 8px; border-radius: 4px; font-weight: 600; }
.annot-group { margin-bottom: 12px; }
.group-title { font-size: 12px; font-weight: 600; margin-bottom: 6px; }
.annot-item { padding: 8px 10px; background: #FAFAF7; border-radius: 6px; border-left: 3px solid #B5C7CB; margin-bottom: 6px; cursor: pointer; transition: all .15s; }
.annot-item:hover { background: #F0EDE6; }
.annot-item.active { background: #EAF0F1; box-shadow: 0 1px 4px rgba(77,128,136,0.15); }
.annot-item-title { font-size: 12px; font-weight: 600; color: #2B2B2B; margin-bottom: 3px; }
.annot-item-content { font-size: 12px; color: #595959; line-height: 1.5; }
.no-annot-hint { font-size: 13px; color: #8C8C8C; text-align: center; padding: 24px 0; }
.select-hint { text-align: center; color: #8C8C8C; padding: 60px 0; font-size: 14px; }
.no-analysis-hint { font-size: 13px; color: #8C8C8C; background: #F8F6F1; padding: 12px; border-radius: 6px; margin-top: 12px; line-height: 1.6; }
</style>
