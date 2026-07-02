<script setup lang="ts">
// 分镜剧本预览面板
// 展示章节的分镜列表（镜头/动作/视觉提示词/时长/音效/BGM）
// 支持生成分镜（后台任务）、导出 JSON
import { API } from '~/composables/api'
import { useBackgroundTasks } from '~/composables/useBackgroundTasks'

const props = defineProps<{
  chapterId: number
  chapterNumber: number
}>()

const emit = defineEmits<{ (e: 'close'): void }>()

const msg = useMessage()
const { trackTask, onTaskCompleted } = useBackgroundTasks()

const visible = ref(false)
const loading = ref(false)
const generating = ref(false)
const screenplay = ref<any>(null)

// 景别图标和颜色
const shotTypeMeta: Record<string, { icon: string; color: string; label: string }> = {
  wide:            { icon: '🏞️', color: '#52A569', label: '远景' },
  medium:          { icon: '🎬', color: '#1677FF', label: '中景' },
  closeup:         { icon: '🔍', color: '#C75B5B', label: '特写' },
  extreme_closeup: { icon: '🔬', color: '#8B2C8B', label: '大特写' },
  aerial:          { icon: '🚁', color: '#D49A4E', label: '航拍' },
}

// 镜头运动标签
const cameraMoveLabel: Record<string, string> = {
  static: '固定',
  slow_push_in: '缓推',
  slow_pull_out: '缓拉',
  pan: '摇摄',
  tilt: '俯仰',
  tracking: '跟随',
  zoom: '变焦',
}

// BGM 标签颜色
const bgmColor: Record<string, string> = {
  calm: 'blue',
  suspense: 'orange',
  battle: 'red',
  sad: 'purple',
  cheerful: 'green',
  mysterious: 'cyan',
  epic: 'gold',
}

const shots = computed(() => {
  if (!screenplay.value?.shots) return []
  return screenplay.value.shots
})

const stats = computed(() => screenplay.value?.stats || {})

// 格式化镜头序号
function shotIndex(item: any, idx: number): number {
  // 跳过 scene_heading 统计 shot 序号
  return idx + 1
}

// 打开面板
async function open() {
  visible.value = true
  await loadScreenplay()
}

// 加载已有分镜
async function loadScreenplay() {
  loading.value = true
  try {
    screenplay.value = await API.chapter.getScreenplay(props.chapterId)
  } catch (e: any) {
    // 404 = 尚未生成
    screenplay.value = null
  } finally {
    loading.value = false
  }
}

// 生成分镜（后台任务）
async function generate() {
  generating.value = true
  try {
    const res = await API.chapter.generateScreenplay(props.chapterId)
    trackTask({
      id: res.task_id,
      task_type: 'chapter_screenplay',
      title: `分镜: 第${props.chapterNumber}章`,
    })
    msg.success('分镜任务已提交，请稍候...')
  } catch (e: any) {
    msg.error('提交失败：' + (e.message || '未知错误'))
  } finally {
    generating.value = false
  }
}

// 任务完成后自动刷新
onTaskCompleted('chapter_screenplay', async () => {
  if (visible.value) {
    await loadScreenplay()
  }
})

// 导出 JSON
function exportJson() {
  if (!screenplay.value) return
  const blob = new Blob([JSON.stringify(screenplay.value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `chapter_${props.chapterNumber}_screenplay.json`
  a.click()
  URL.revokeObjectURL(url)
}

// 复制文本
async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    msg.success('已复制')
  } catch {
    msg.warning('复制失败，请手动选择')
  }
}

defineExpose({ open })
</script>

<template>
  <a-modal
    v-model:open="visible"
    :title="`🎬 分镜剧本 · 第${chapterNumber}章`"
    width="90%"
    :style="{ top: '20px' }"
    :footer="null"
    :destroy-on-close="true"
    @cancel="emit('close')"
  >
    <!-- 操作栏 -->
    <div style="margin-bottom: 16px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
      <a-button type="primary" :loading="generating" @click="generate">
        {{ generating ? '提交中...' : (screenplay ? '🔄 重新生成' : '🎬 生成分镜') }}
      </a-button>
      <a-button v-if="screenplay" @click="exportJson">📥 导出 JSON</a-button>
      <a-button @click="loadScreenplay" :loading="loading">🔄 刷新</a-button>
      <span v-if="screenplay?.created_at" style="color: #999; font-size: 12px;">
        生成于 {{ new Date(screenplay.created_at).toLocaleString('zh-CN') }}
      </span>
    </div>

    <!-- 统计栏 -->
    <div v-if="screenplay && stats.shot_count" style="margin-bottom: 16px;">
      <a-row :gutter="16">
        <a-col :span="4">
          <a-statistic title="镜头数" :value="stats.shot_count" />
        </a-col>
        <a-col :span="4">
          <a-statistic title="场景数" :value="stats.scene_count" />
        </a-col>
        <a-col :span="4">
          <a-statistic title="预计时长" :value="stats.total_duration_display" />
        </a-col>
        <a-col :span="12">
          <div style="padding-top: 20px;">
            <a-tag v-for="(count, type) in stats.shot_type_distribution" :key="type" :color="shotTypeMeta[type]?.color">
              {{ shotTypeMeta[type]?.icon }} {{ shotTypeMeta[type]?.label || type }}: {{ count }}
            </a-tag>
          </div>
        </a-col>
      </a-row>
    </div>

    <!-- 加载中 -->
    <a-spin v-if="loading" tip="加载中..." />

    <!-- 空状态 -->
    <a-empty v-else-if="!screenplay" description="尚未生成分镜剧本">
      <template #extra>
        <a-button type="primary" :loading="generating" @click="generate">🎬 开始生成</a-button>
      </template>
    </a-empty>

    <!-- 分镜列表 -->
    <div v-else class="screenplay-list">
      <template v-for="(item, idx) in shots" :key="idx">
        <!-- 场景标题 -->
        <div v-if="item.scene_heading" class="scene-heading">
          <span class="scene-icon">🎬</span>
          <span class="scene-label">场景切换</span>
          <a-tag color="blue">{{ item.scene_change }}</a-tag>
          <span v-if="item.location" class="scene-detail">📍 {{ item.location }}</span>
          <span v-if="item.time_of_day" class="scene-detail">🕐 {{ item.time_of_day }}</span>
          <span v-if="item.mood" class="scene-detail">🎭 {{ item.mood }}</span>
        </div>

        <!-- 分镜卡片 -->
        <div v-else class="shot-card">
          <!-- 左侧：镜头序号 + 景别 -->
          <div class="shot-left">
            <div class="shot-number">{{ shotIndex(item, idx) }}</div>
            <div class="shot-type-icon">{{ shotTypeMeta[item.shot_type]?.icon || '🎬' }}</div>
            <a-tag :color="shotTypeMeta[item.shot_type]?.color || '#8C8C8C'" size="small">
              {{ shotTypeMeta[item.shot_type]?.label || item.shot_type }}
            </a-tag>
            <a-tag v-if="item.camera_move && item.camera_move !== 'static'" size="small">
              🎥 {{ cameraMoveLabel[item.camera_move] || item.camera_move }}
            </a-tag>
            <div class="shot-duration">{{ item.duration }}s</div>
          </div>

          <!-- 右侧：内容 -->
          <div class="shot-content">
            <!-- 画面动作 -->
            <div v-if="item.action" class="shot-action">
              <span class="field-label">画面</span>
              {{ item.action }}
            </div>

            <!-- 台词/旁白 -->
            <div v-if="item.text" class="shot-dialogue">
              <span class="field-label">{{ item.speaker === 'Narrator' ? '旁白' : item.speaker }}</span>
              <span class="dialogue-text">"{{ item.text }}"</span>
              <a-tag v-if="item.emotion" size="small" color="orange">{{ item.emotion }}</a-tag>
            </div>

            <!-- 视觉提示词（可复制） -->
            <div v-if="item.visual_prompt" class="shot-visual-prompt">
              <div class="prompt-header">
                <span class="field-label">🎨 画面提示词</span>
                <a-button type="link" size="small" @click="copyText(item.visual_prompt)">复制</a-button>
              </div>
              <div class="prompt-text">{{ item.visual_prompt }}</div>
              <div v-if="item.negative_prompt" class="negative-prompt">
                <span style="color: #999;">负面：</span>{{ item.negative_prompt }}
              </div>
            </div>

            <!-- 音效 + BGM -->
            <div v-if="item.sfx?.length || item.bgm_tag" class="shot-audio">
              <template v-if="item.sfx?.length">
                <span class="field-label">🔊 音效</span>
                <a-tag v-for="sfx in item.sfx" :key="sfx" size="small">{{ sfx }}</a-tag>
              </template>
              <template v-if="item.bgm_tag">
                <span class="field-label" style="margin-left: 12px;">🎵 BGM</span>
                <a-tag :color="bgmColor[item.bgm_tag] || 'default'" size="small">{{ item.bgm_tag }}</a-tag>
              </template>
            </div>
          </div>
        </div>
      </template>
    </div>
  </a-modal>
</template>

<style scoped>
.screenplay-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.scene-heading {
  background: linear-gradient(135deg, #e8f4fd, #f0f7ff);
  border-left: 4px solid #1677ff;
  padding: 10px 16px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.scene-icon { font-size: 18px; }
.scene-label { font-weight: 600; color: #1677ff; }
.scene-detail { color: #666; font-size: 13px; }

.shot-card {
  display: flex;
  gap: 16px;
  padding: 16px;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  background: #fafafa;
  transition: box-shadow 0.2s;
}
.shot-card:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

.shot-left {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  min-width: 70px;
}
.shot-number {
  font-size: 18px;
  font-weight: 700;
  color: #999;
  line-height: 1;
}
.shot-type-icon {
  font-size: 24px;
}
.shot-duration {
  font-size: 13px;
  color: #D49A4E;
  font-weight: 600;
}

.shot-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-label {
  font-size: 12px;
  color: #999;
  margin-right: 6px;
}

.shot-action {
  font-size: 14px;
  color: #333;
  line-height: 1.6;
}

.shot-dialogue {
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.dialogue-text {
  font-family: 'Noto Serif SC', serif;
  color: #555;
}

.shot-visual-prompt {
  background: #f5f5f5;
  border-radius: 6px;
  padding: 8px 12px;
}
.prompt-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.prompt-text {
  font-size: 13px;
  color: #555;
  font-family: monospace;
  line-height: 1.5;
  margin-top: 4px;
  word-break: break-word;
}
.negative-prompt {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}

.shot-audio {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}
</style>
