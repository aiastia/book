/**
 * 标注类型元数据与分组工具
 * 统一 chapter-reader.vue / chapters.vue / ChapterAnalysisPanel.vue 中的重复定义
 */

export interface AnnotationTypeMeta {
  label: string
  color: string
  icon: string
  bg: string
  border: string
}

export const annotationTypeMeta: Record<string, AnnotationTypeMeta> = {
  hook: { label: '剧情钩子', color: '#C75B5B', icon: '🎣', bg: '#FFF1F0', border: '#FFCCC7' },
  foreshadow: { label: '伏笔', color: '#1677FF', icon: '🔮', bg: '#E6F7FF', border: '#91D5FF' },
  plot_point: { label: '关键情节', color: '#52A569', icon: '⭐', bg: '#F6FFED', border: '#B7EB8F' },
  character_event: { label: '角色事件', color: '#D49A4E', icon: '👤', bg: '#FFF7E6', border: '#FFD591' },
}

export interface AnnotationGroup {
  type: string
  label: string
  icon: string
  color: string
  items: any[]
}

export function useAnnotationTypes() {
  /** 将标注数组按类型分组，过滤空组 */
  function groupAnnotations(annotations: any[]): AnnotationGroup[] {
    const groups: Record<string, any[]> = { hook: [], foreshadow: [], plot_point: [], character_event: [] }
    for (const a of annotations || []) {
      if (a && a.type && groups[a.type]) groups[a.type].push(a)
    }
    return (Object.keys(annotationTypeMeta) as string[])
      .map(type => ({
        type,
        label: annotationTypeMeta[type].label,
        icon: annotationTypeMeta[type].icon,
        color: annotationTypeMeta[type].color,
        items: groups[type],
      }))
      .filter(g => g.items.length > 0)
  }

  return { annotationTypeMeta, groupAnnotations }
}
