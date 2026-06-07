<script setup lang="ts">
// 写作风格：7 维度配置 + 项目默认绑定（#24 增强）
import { useProject } from '~/composables/useProject'
useHead({ title: '写作风格 — 墨语' })
const msg = useMessage()
const { currentProjectId } = useProject()
const { data: styles, refresh } = await useApi<any[]>('/api/writing-styles', { key: 'writing-styles' })

const showEdit = ref(false)
const editingStyle = ref<any>(null)
const isNew = ref(false)
const editForm = reactive({
  name: '',
  description: '',
  config: {
    pacing: '中',           // 快/中/慢
    tone: '平实',           // 热血/沉静/幽默/紧张/庄重/平实
    sentence_length: '长短结合', // 短句/长短结合/长句
    description_focus: '动作',   // 动作/心理/环境/对话/线索
    dialogue_ratio: '中',   // 高/中/低
    vocabulary: '通俗',      // 通俗/文雅/华丽
    pov: '第三人称',         // 第一/第三/全知
  } as Record<string, string>,
})

const optionGroups: Record<string, string[]> = {
  pacing: ['快', '中', '慢'],
  tone: ['热血', '沉静', '幽默', '紧张', '庄重', '平实'],
  sentence_length: ['短句为主', '长短结合', '长句为主'],
  description_focus: ['动作', '心理', '环境', '对话', '线索'],
  dialogue_ratio: ['高', '中', '低'],
  vocabulary: ['通俗', '文雅', '华丽'],
  pov: ['第一人称', '第三人称', '全知视角'],
}
const labels: Record<string, string> = {
  pacing: '节奏', tone: '基调', sentence_length: '句式',
  description_focus: '描写侧重', dialogue_ratio: '对话占比',
  vocabulary: '用词风格', pov: '叙事视角',
}

function openAdd() {
  isNew.value = true
  editingStyle.value = null
  editForm.name = ''
  editForm.description = ''
  editForm.config = { pacing: '中', tone: '平实', sentence_length: '长短结合', description_focus: '动作', dialogue_ratio: '中', vocabulary: '通俗', pov: '第三人称' }
  showEdit.value = true
}
function openEdit(s: any) {
  isNew.value = false
  editingStyle.value = s
  editForm.name = s.name
  editForm.description = s.description || ''
  const cfg = s.config || {}
  editForm.config = {
    pacing: cfg.pacing || '中',
    tone: cfg.tone || '平实',
    sentence_length: cfg.sentence_length || '长短结合',
    description_focus: cfg.description_focus || '动作',
    dialogue_ratio: cfg.dialogue_ratio || '中',
    vocabulary: cfg.vocabulary || '通俗',
    pov: cfg.pov || '第三人称',
  }
  showEdit.value = true
}

async function onSave() {
  if (!editForm.name.trim()) { msg.warning('请输入名称'); return }
  try {
    if (isNew.value) {
      await apiPost('/api/writing-styles', { name: editForm.name, description: editForm.description, config: editForm.config })
    } else {
      await apiPut(`/api/writing-styles/${editingStyle.value.id}`, { name: editForm.name, description: editForm.description, config: editForm.config })
    }
    showEdit.value = false
    msg.success('已保存')
    await refresh()
  } catch (e: any) { msg.error('保存失败：' + formatError(e)) }
}
async function onDelete(id: number) {
  if (!await msg.confirm('确认删除？')) return
  try { await apiDelete(`/api/writing-styles/${id}`); await refresh(); msg.success('已删除') }
  catch (e: any) { msg.error('删除失败：' + formatError(e)) }
}
async function onApplyToProject(id: number) {
  if (!currentProjectId.value) { msg.warning('请先选择项目'); return }
  try {
    await apiPost(`/api/writing-styles/${id}/apply/${currentProjectId.value}`, {})
    msg.success('已设为当前项目默认风格')
  } catch (e: any) { msg.error('设置失败：' + formatError(e)) }
}
</script>

<template>
  <PageHeader title="写作风格">
    <template #actions>
      <a-button @click="openAdd">+ 新建风格</a-button>
      <a-button @click="refresh()">刷新</a-button>
    </template>
  </PageHeader>

  <div class="page-content">
    <a-alert type="info" :closable="false" style="margin-bottom:16px;"
      message="写作风格从 7 个维度定义：节奏/基调/句式/描写侧重/对话占比/用词/视角。设为项目默认后，AI 生成章节会自动遵循。" />

    <div v-if="styles && styles.length" class="style-grid">
      <a-card v-for="s in styles" :key="s.id" hoverable :class="{ preset: s.is_preset }">
        <div class="card-head">
          <div>
            <div class="style-name">{{ s.name }}</div>
            <div class="style-desc">{{ s.description }}</div>
          </div>
          <a-tag v-if="s.is_preset" color="blue" size="small">预设</a-tag>
        </div>
        <!-- 7 维度展示 -->
        <div class="dim-grid">
          <div v-for="(opts, key) in optionGroups" :key="key" class="dim-chip" :class="{ active: (s.config||{})[key] === opts[0] }">
            <span class="dim-label">{{ labels[key] }}</span>
            <span class="dim-value" :style="{ color: '#4D8088' }">{{ (s.config||{})[key] || '—' }}</span>
          </div>
        </div>
        <div class="card-actions">
          <a-button size="small" type="primary" @click="onApplyToProject(s.id)">设为项目默认</a-button>
          <a-button size="small" @click="openEdit(s)">编辑</a-button>
          <a-button v-if="!s.is_preset" size="small" danger @click="onDelete(s.id)">删除</a-button>
        </div>
      </a-card>
    </div>
    <a-empty v-else description="暂无风格" />
  </div>

  <!-- 编辑/新建弹窗 -->
  <a-modal v-model:open="showEdit" :title="isNew ? '新建风格' : `编辑 — ${editForm.name}`" width="560px" :destroy-on-close="true">
    <a-form layout="vertical">
      <a-form-item label="风格名称"><a-input v-model:value="editForm.name" /></a-form-item>
      <a-form-item label="描述"><a-textarea v-model:value="editForm.description" :rows="2" /></a-form-item>
      <a-divider orientation="left">维度配置</a-divider>
      <div v-for="(opts, key) in optionGroups" :key="key" class="dim-row">
        <span class="dim-row-label">{{ labels[key] }}</span>
        <a-radio-group v-model:value="editForm.config[key]" size="small" button-style="solid">
          <a-radio-button v-for="o in opts" :key="o" :value="o">{{ o }}</a-radio-button>
        </a-radio-group>
      </div>
    </a-form>
    <template #footer>
      <a-button @click="showEdit = false">取消</a-button>
      <a-button type="primary" @click="onSave">保存</a-button>
    </template>
  </a-modal>
</template>

<style scoped>
.style-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 14px; }
.card-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
.style-name { font-weight: 600; font-size: 15px; margin-bottom: 4px; }
.style-desc { font-size: 12px; color: #8C8C8C; }
.dim-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 12px; }
.dim-chip { display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: #F8F6F1; border-radius: 6px; font-size: 12px; }
.dim-label { color: #8C8C8C; }
.dim-value { font-weight: 600; }
.dim-chip.active { background: #EAF0F1; }
.card-actions { display: flex; gap: 6px; border-top: 1px solid #F0EDE6; padding-top: 10px; }
.dim-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.dim-row-label { font-size: 13px; color: #595959; min-width: 70px; }
</style>
