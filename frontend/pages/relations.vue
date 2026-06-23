<script setup lang="ts">
// 角色关系：Vue Flow 图谱视图 + 表格视图（#17）
// Vue Flow 提供拖拽/缩放/自动布局，对标 MuMuAINovel ReactFlow
import { VueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import { useProjectApi } from '~/composables/useProjectApi'
import { useProject } from '~/composables/useProject'
useHead({ title: '角色关系 — 墨语' })
const { currentProjectId } = useProject()
if (!currentProjectId.value) await navigateTo('/books')

const api = useProjectApi()
const msg = useMessage()
const { data: graph, refresh } = await api.getRelationGraph()

// 视图切换
const viewMode = ref<'chart' | 'table'>('chart')

// 关系类型 → 颜色
const categoryColor: Record<string, string> = {
  family: '#e91e63', romantic: '#ff5722', hostile: '#f44336',
  professional: '#2196f3', social: '#6B9CA4',
}
const categoryLabel: Record<string, string> = {
  family: '亲情', romantic: '情感', hostile: '敌对',
  professional: '职业', social: '社交',
}

// Vue Flow 节点/边
const vfNodes = ref<any[]>([])
const vfEdges = ref<any[]>([])

function buildGraph() {
  if (!graph.value) return
  const ns = graph.value.nodes || []
  const es = graph.value.edges || []
  // 圆形布局作为初始位置（用户可拖拽调整）
  const cx = 400, cy = 300, r = 200
  vfNodes.value = ns.map((n: any, i: number) => {
    const isMain = n.role === '主角'
    const angle = (2 * Math.PI * i) / Math.max(ns.length, 1) - Math.PI / 2
    return {
      id: String(n.id),
      position: { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) },
      data: { label: n.name, role: n.role, isMain },
      type: 'character',
      style: {
        background: isMain ? '#4D8088' : '#5A9098',
        color: '#fff',
        border: 'none',
        borderRadius: '50%',
        width: '70px',
        height: '70px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: '13px',
        fontWeight: isMain ? '700' : '500',
        textAlign: 'center' as const,
      },
    }
  })
  vfEdges.value = es.map((e: any, i: number) => {
    const color = categoryColor[e.category] || '#999'
    return {
      id: `e${i}`,
      source: String(e.source),
      target: String(e.target),
      label: e.relation_type,
      animated: Math.abs(e.intimacy) > 50,
      style: { stroke: color, strokeWidth: Math.abs(e.intimacy) > 50 ? 2.5 : 1.5 },
      labelStyle: { fill: color, fontSize: 11, fontWeight: 600 },
      labelBgStyle: { fill: '#fff' },
      type: e.intimacy < 0 ? 'step' : 'default',
    }
  })
}
watch(graph, buildGraph, { immediate: true })

// 自动布局（简单的力导向 - 居中分布）
function autoLayout() {
  buildGraph()
  msg.info('已重置布局，可拖拽节点调整位置')
}

// 表格视图数据
const tableData = computed(() => {
  if (!graph.value) return []
  const nameMap = new Map<number, string>()
  ;(graph.value.nodes || []).forEach((n: any) => nameMap.set(n.id, n.name))
  return (graph.value.edges || []).map((e: any, i: number) => ({
    key: i,
    char_a: nameMap.get(e.source) || `#${e.source}`,
    char_b: nameMap.get(e.target) || `#${e.target}`,
    relation_type: e.relation_type,
    category: e.category,
    category_label: categoryLabel[e.category] || '其他',
    intimacy: e.intimacy,
    status: e.status || 'active',
  }))
})
const tableColumns = [
  { title: '角色 A', dataIndex: 'char_a', key: 'char_a', width: 120 },
  { title: '关系', dataIndex: 'relation_type', key: 'relation_type', width: 120 },
  { title: '角色 B', dataIndex: 'char_b', key: 'char_b', width: 120 },
  { title: '分类', dataIndex: 'category_label', key: 'category_label', width: 100 },
  { title: '亲密度', dataIndex: 'intimacy', key: 'intimacy', width: 120, sorter: (a: any, b: any) => a.intimacy - b.intimacy },
]

// 重建
const showRebuild = ref(false)
async function rebuild() {
  if (!await msg.confirm('AI 将重新分析所有角色关系，可能需要 30-60 秒，期间请勿离开页面。确认开始？')) return
  showRebuild.value = true
  msg.info('AI 正在分析角色关系，请耐心等待…')
  try {
    await api.autoRebuildRelations()
    msg.success('AI 已重新分析角色关系')
    await refresh()
  } catch (e: any) {
    msg.error('分析失败：' + formatError(e))
  } finally {
    showRebuild.value = false
  }
}
</script>

<template>
  <PageHeader title="🗺️ 角色关系图谱">
    <template #actions>
      <a-radio-group v-model:value="viewMode" button-style="solid" size="small">
        <a-radio-button value="chart">图谱视图</a-radio-button>
        <a-radio-button value="table">表格视图</a-radio-button>
      </a-radio-group>
      <a-button v-if="viewMode === 'chart'" size="small" @click="autoLayout">🔄 重置布局</a-button>
      <a-button type="primary" :loading="showRebuild" @click="rebuild">{{ showRebuild ? '分析中（请等待）…' : '🤖 AI 重新分析' }}</a-button>
    </template>
  </PageHeader>

  <div class="page-content">
    <a-alert v-if="!graph?.nodes?.length" message="暂无角色，请先在「角色设定」中创建角色" type="info" show-icon />

    <template v-else>
      <!-- Vue Flow 图谱视图 -->
      <div v-if="viewMode === 'chart'" class="chart-wrap">
        <div class="flow-card">
          <ClientOnly>
            <VueFlow :nodes="vfNodes" :edges="vfEdges" :default-viewport="{ zoom: 0.8 }" fit-view-on-init>
              <Background />
              <Controls />
              <MiniMap />
            </VueFlow>
            <template #fallback>
              <div style="height:500px;display:flex;align-items:center;justify-content:center;color:#8C8C8C;">加载关系图谱…</div>
            </template>
          </ClientOnly>
        </div>
        <div class="legend">
          <span v-for="(label, key) in categoryLabel" :key="key" class="legend-item">
            <span class="dot" :style="{ background: categoryColor[key] }"></span>{{ label }}
          </span>
          <span class="legend-hint">💡 可拖拽节点调整位置，滚轮缩放</span>
        </div>
      </div>

      <!-- 表格视图 -->
      <div v-else>
        <div class="legend" style="margin-bottom: 12px">
          <span v-for="(label, key) in categoryLabel" :key="key" class="legend-item">
            <span class="dot" :style="{ background: categoryColor[key] }"></span>{{ label }}
          </span>
        </div>
        <a-table :columns="tableColumns" :data-source="tableData" :pagination="{ pageSize: 15 }" size="middle">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'relation_type'">
              <span class="rel-type" :style="{ color: categoryColor[record.category] }">{{ record.relation_type }}</span>
            </template>
            <template v-else-if="column.key === 'category_label'">
              <a-tag :color="{ family: 'pink', romantic: 'orange', hostile: 'red', professional: 'blue', social: 'cyan' }[record.category] || 'default'">
                {{ record.category_label }}
              </a-tag>
            </template>
            <template v-else-if="column.key === 'intimacy'">
              <span :class="['intimacy', { negative: record.intimacy < 0 }]">
                {{ record.intimacy > 0 ? '+' : '' }}{{ record.intimacy }}
              </span>
            </template>
          </template>
        </a-table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.chart-wrap { display: flex; flex-direction: column; gap: 12px; }
.flow-card { background: #fafafa; border: 1px solid #e8e8e8; border-radius: 8px; height: 540px; overflow: hidden; }
/* Vue Flow 根元素需撑满容器高度才可见 */
.flow-card :deep(.vue-flow) { width: 100%; height: 100%; }
.legend { display: flex; gap: 14px; font-size: 12px; flex-wrap: wrap; align-items: center; }
.legend-item { display: flex; align-items: center; gap: 4px; }
.legend-hint { color: #B5C7CB; font-size: 11px; margin-left: auto; }
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.rel-type { font-weight: 600; }
.intimacy { color: #6B9CA4; font-weight: 600; }
.intimacy.negative { color: #f44336; }
</style>
