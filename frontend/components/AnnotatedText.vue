<script setup lang="ts">
// 带标注的文本渲染（#8 章节阅读器）
// 把章节正文按标注的 position 切段，高亮标注部分。
// 对标 MuMuAINovel AnnotatedText.tsx。
interface Annotation {
  type: 'hook' | 'foreshadow' | 'plot_point' | 'character_event'
  subtype?: string
  title?: string
  content?: string
  position: number
  length: number
  metadata?: any
}
const props = defineProps<{
  content: string
  annotations: Annotation[]
  activeId?: string | number | null
}>()
const emit = defineEmits<{ (e: 'select', ann: Annotation): void }>()

// 标注类型配色
const typeColor: Record<string, { bg: string; border: string; text: string; label: string }> = {
  hook: { bg: '#FFF1F0', border: '#FFCCC7', text: '#C75B5B', label: '钩子' },
  foreshadow: { bg: '#E6F7FF', border: '#91D5FF', text: '#1677FF', label: '伏笔' },
  plot_point: { bg: '#F6FFED', border: '#B7EB8F', text: '#52A569', label: '情节点' },
  character_event: { bg: '#FFF7E6', border: '#FFD591', text: '#D49A4E', label: '角色' },
}

// 生成标注唯一 ID
function annId(a: Annotation, idx: number) {
  return `${a.type}-${a.position}`
}

// 判断标注是否激活
function isActive(anns: Annotation[]): boolean {
  if (!props.activeId || !anns.length) return false
  return anns.some(a => annId(a, 0) === props.activeId)
}

// 把内容切成段（处理重叠标注）
interface Segment {
  text: string
  annotations: Annotation[]
  start: number
}
const segments = computed<Segment[]>(() => {
  if (!props.content) return []
  // 过滤有效标注
  const valid = (props.annotations || [])
    .filter(a => a.position >= 0 && a.position < props.content.length && a.length > 0)
    .sort((a, b) => a.position - b.position)

  if (!valid.length) return [{ text: props.content, annotations: [], start: 0 }]

  // 收集所有断点
  const points = new Set<number>([0, props.content.length])
  for (const a of valid) {
    points.add(a.position)
    points.add(Math.min(a.position + a.length, props.content.length))
  }
  const sorted = [...points].filter(p => p >= 0 && p <= props.content.length).sort((a, b) => a - b)

  const result: Segment[] = []
  for (let i = 0; i < sorted.length - 1; i++) {
    const start = sorted[i]
    const end = sorted[i + 1]
    if (start >= end) continue
    // 找覆盖此段的标注
    const covers = valid.filter(a => a.position < end && a.position + a.length > start)
    result.push({
      text: props.content.slice(start, end),
      annotations: covers,
      start,
    })
  }
  return result
})

function segStyle(anns: Annotation[]) {
  if (!anns.length) return {}
  const c = typeColor[anns[0].type] || typeColor.plot_point
  const active = isActive(anns)
  return {
    background: active ? c.border : c.bg,
    borderBottom: `2px solid ${c.border}`,
    color: c.text,
    boxShadow: active ? `0 0 0 2px ${c.border}` : 'none',
    transform: active ? 'scale(1.02)' : 'none',
  }
}
function onSegClick(anns: Annotation[]) {
  if (anns.length) emit('select', anns[0])
}
// 给每个标注生成唯一 id（用于高亮定位）
function annKey(a: Annotation, idx: number) {
  return `${a.type}-${a.position}-${idx}`
}
</script>

<template>
  <div class="annotated-text">
    <span
      v-for="(seg, i) in segments" :key="i"
      :class="['seg', { annotated: seg.annotations.length, clickable: seg.annotations.length }]"
      :style="segStyle(seg.annotations)"
      @click="seg.annotations.length && onSegClick(seg.annotations)"
    >
      {{ seg.text }}
    </span>
  </div>
</template>

<style scoped>
.annotated-text { font-size: 15px; line-height: 2; color: #2B2B2B; white-space: pre-wrap; word-break: break-word; }
.seg { transition: all .2s ease; }
.seg.annotated { padding: 1px 2px; border-radius: 3px; cursor: pointer; }
.seg.clickable:hover { filter: brightness(0.96); }
</style>
