<script setup lang="ts">
// 写作风格：7 维度配置 + 项目默认绑定（#24 增强）
import { useProject } from '~/composables/useProject'
import { apiGet } from '~/composables/useApi'
useHead({ title: '写作风格 — 墨语' })
const msg = useMessage()
const { currentProjectId } = useProject()
const { data: styles, refresh } = await useApi<any[]>('/api/writing-styles', { key: 'writing-styles' })

// 当前项目默认风格名（用于在卡片上标识哪个是项目默认）
const projectDefaultStyleName = ref<string>('')
async function loadProjectDefault() {
  if (!currentProjectId.value) return
  try {
    const p = await apiGet<any>(`/api/projects/${currentProjectId.value}`)
    projectDefaultStyleName.value = p?.writing_style?.name || ''
  } catch {}
}
if (import.meta.client) loadProjectDefault()
const isProjectDefault = (s: any) => !!projectDefaultStyleName.value && s.name === projectDefaultStyleName.value

const showEdit = ref(false)
const editingStyle = ref<any>(null)
const isNew = ref(false)
const editForm = reactive({
  name: '',
  description: '',
  author_name: '',      // 作家名（可选，如"鲁迅"）
  custom_prompt: '',   // 用户自定义提示词（高级，优先于维度配置）
  config: {
    pacing: '中',                // 快/中/慢（单选）
    tone: ['平实'],              // 热血/沉静/幽默/紧张/庄重/平实（多选）
    sentence_length: '长短结合', // 短句/长短结合/长句（单选）
    description_focus: ['动作'], // 动作/心理/环境/对话/线索（多选）
    dialogue_ratio: '中',        // 高/中/低（单选）
    vocabulary: ['通俗'],        // 通俗/文雅/华丽（多选）
    pov: '第三人称',             // 第一/第三/全知（单选）
    disable_dimensions: false,   // 是否关闭维度配置注入（true=不注入③）
  } as Record<string, any>,
  reference_text: '',   // 范文原文（few-shot 原料）
  style_traits: {} as Record<string, string>,  // AI 提炼出的结构化特征
})
const analyzeLoading = ref(false)
// 是否已提炼出文风特征（用于 ②自定义提示词 的互斥提示）
const hasStyleTraits = computed(() => Object.keys(editForm.style_traits || {}).length > 0)

// 文风特征各维度的中文标签
const traitLabels: Record<string, string> = {
  sentence_pattern: '句式节奏',
  vocabulary: '用词',
  imagery: '意象与感官',
  rhythm: '篇章节奏',
  tone: '语气与态度',
  signature_techniques: '标志手法',
  avoid_list: '需避开的反面',
  summary: '总纲',
}

const optionGroups: Record<string, string[]> = {
  pacing: ['快', '中', '慢'],
  tone: ['热血', '沉静', '幽默', '紧张', '庄重', '平实', '温馨', '沧桑', '讽刺', '诡异'],
  sentence_length: ['短句为主', '长短结合', '长句为主'],
  description_focus: ['动作', '心理', '环境', '对话', '线索'],
  dialogue_ratio: ['高', '中', '低'],
  vocabulary: ['通俗', '文雅', '华丽', '古雅', '冷峻', '诗意', '粗犷'],
  pov: ['第一人称', '第三人称', '全知视角'],
}
const labels: Record<string, string> = {
  pacing: '节奏', tone: '基调', sentence_length: '句式',
  description_focus: '描写侧重', dialogue_ratio: '对话占比',
  vocabulary: '用词风格', pov: '叙事视角',
}
// 支持多选的维度（其余为单选）。多选维度的值存为数组，单选存为字符串。
const multiKeys = new Set(['tone', 'description_focus', 'vocabulary'])
const isMulti = (key: string) => multiKeys.has(key)
// 归一化：把任意来源（字符串/数组/null）转成该维度应有的形态
const normValue = (key: string, raw: any) => {
  if (isMulti(key)) {
    const arr = Array.isArray(raw) ? raw : (raw ? [raw] : [])
    return arr
  }
  return raw || ''
}
// 把维度值格式化为展示文本（数组用顿号连接）
const fmtValue = (key: string, raw: any) => {
  if (isMulti(key)) {
    const arr = Array.isArray(raw) ? raw : (raw ? [raw] : [])
    return arr.length ? arr.join('、') : '—'
  }
  return raw || '—'
}
// 多选维度的按钮块交互：判断某选项是否被选中
const isPicked = (key: string, opt: string) => {
  const v = editForm.config[key]
  return Array.isArray(v) ? v.includes(opt) : v === opt
}
// 多选维度的按钮块交互：点击切换选中态
const togglePick = (key: string, opt: string) => {
  const v = editForm.config[key]
  const arr = Array.isArray(v) ? [...v] : (v ? [v] : [])
  const i = arr.indexOf(opt)
  if (i >= 0) arr.splice(i, 1)
  else arr.push(opt)
  editForm.config[key] = arr
}

// 各维度的默认值（新建时使用）
const defaultConfig: Record<string, any> = {
  pacing: '中',
  tone: ['平实'],
  sentence_length: '长短结合',
  description_focus: ['动作'],
  dialogue_ratio: '中',
  vocabulary: ['通俗'],
  pov: '第三人称',
}
function openAdd() {
  isNew.value = true
  editingStyle.value = null
  editForm.name = ''
  editForm.description = ''
  editForm.author_name = ''
  editForm.custom_prompt = ''
  editForm.reference_text = ''
  editForm.style_traits = {}
  editForm.config = { ...defaultConfig, tone: [...defaultConfig.tone], description_focus: [...defaultConfig.description_focus], vocabulary: [...defaultConfig.vocabulary], disable_dimensions: false }
  showEdit.value = true
}
function openEdit(s: any) {
  isNew.value = false
  editingStyle.value = s
  editForm.name = s.name
  editForm.description = s.description || ''
  editForm.author_name = s.author_name || ''
  editForm.custom_prompt = s.custom_prompt || ''
  editForm.reference_text = s.reference_text || ''
  editForm.style_traits = s.style_traits || {}
  const cfg = s.config || {}
  editForm.config = {
    pacing: normValue('pacing', cfg.pacing),
    tone: normValue('tone', cfg.tone),
    sentence_length: normValue('sentence_length', cfg.sentence_length),
    description_focus: normValue('description_focus', cfg.description_focus),
    dialogue_ratio: normValue('dialogue_ratio', cfg.dialogue_ratio),
    vocabulary: normValue('vocabulary', cfg.vocabulary),
    pov: normValue('pov', cfg.pov),
    disable_dimensions: !!cfg.disable_dimensions,
  }
  showEdit.value = true
}

async function onSave() {
  if (!editForm.name.trim()) { msg.warning('请输入名称'); return }
  try {
    const payload = {
      name: editForm.name, description: editForm.description,
      author_name: editForm.author_name, config: editForm.config,
      custom_prompt: editForm.custom_prompt,
      reference_text: editForm.reference_text, style_traits: editForm.style_traits,
    }
    if (isNew.value) {
      await apiPost('/api/writing-styles', payload)
    } else {
      await apiPut(`/api/writing-styles/${editingStyle.value.id}`, payload)
    }
    showEdit.value = false
    msg.success('已保存')
    await refresh()
  } catch (e: any) { msg.error('保存失败：' + formatError(e)) }
}

// AI 提炼文风特征：需先保存（拿到 id）才能调用 analyze 接口
async function onAnalyze() {
  if (!editForm.reference_text.trim()) { msg.warning('请先粘贴范文，再提炼'); return }
  if (isNew.value) {
    msg.info('请先保存风格，再点击「提炼」按钮')
    return
  }
  // 范文可能刚改过未保存，先保存再分析，保证后端读到的是最新范文
  try {
    await apiPut(`/api/writing-styles/${editingStyle.value.id}`, {
      name: editForm.name, description: editForm.description,
      author_name: editForm.author_name, config: editForm.config,
      custom_prompt: editForm.custom_prompt, reference_text: editForm.reference_text,
      style_traits: editForm.style_traits,
    })
  } catch (e: any) {
    msg.error('保存范文失败：' + formatError(e)); return
  }
  analyzeLoading.value = true
  try {
    const res = await apiPost<{ style_traits: Record<string, string> }>(`/api/writing-styles/${editingStyle.value.id}/analyze`, {})
    editForm.style_traits = res?.style_traits || {}
    msg.success('文风特征已提炼完成')
  } catch (e: any) {
    msg.error('提炼失败：' + formatError(e))
  } finally {
    analyzeLoading.value = false
  }
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
    // 更新本地默认标识（避免整页刷新）
    const s = (styles.value || []).find((x: any) => x.id === id)
    if (s) projectDefaultStyleName.value = s.name
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
      <a-card v-for="s in styles" :key="s.id" hoverable :class="{ preset: s.is_preset, 'is-default': isProjectDefault(s) }">
        <div class="card-head">
          <div>
            <div class="style-name">
              {{ s.name }}
              <a-tag v-if="isProjectDefault(s)" color="success" size="small">✓ 当前项目默认</a-tag>
              <a-tag v-if="s.reference_text" color="purple" size="small">📝 范文</a-tag>
              <a-tag v-if="s.author_name" size="small">{{ s.author_name }}</a-tag>
            </div>
            <div class="style-desc">{{ s.description }}</div>
          </div>
          <a-tag v-if="s.is_preset" color="blue" size="small">预设</a-tag>
        </div>
        <!-- 7 维度展示 -->
        <div class="dim-grid">
          <div v-for="(opts, key) in optionGroups" :key="key" class="dim-chip" :class="{ active: (s.config||{})[key] === opts[0] }">
            <span class="dim-label">{{ labels[key] }}</span>
            <span class="dim-value" :style="{ color: '#4D8088' }">{{ fmtValue(key, (s.config||{})[key]) }}</span>
          </div>
        </div>
        <!-- 自定义提示词预览 -->
        <div v-if="s.custom_prompt" class="custom-prompt-box">
          <span class="custom-prompt-label">📝 自定义提示词</span>
          <div class="custom-prompt-text">{{ s.custom_prompt }}</div>
        </div>
        <div class="card-actions">
          <a-button v-if="!isProjectDefault(s)" size="small" type="primary" @click="onApplyToProject(s.id)">设为项目默认</a-button>
          <a-button v-else size="small" disabled>已是项目默认</a-button>
          <a-button size="small" @click="openEdit(s)">编辑</a-button>
          <a-button v-if="!s.is_preset" size="small" danger @click="onDelete(s.id)">删除</a-button>
        </div>
      </a-card>
    </div>
    <a-empty v-else description="暂无风格" />
  </div>

  <!-- 编辑/新建弹窗 -->
  <a-modal v-model:open="showEdit" :title="isNew ? '新建风格' : `编辑 — ${editForm.name}`" width="620px" :destroy-on-close="true">
    <a-form layout="vertical">
      <a-form-item label="风格名称"><a-input v-model:value="editForm.name" /></a-form-item>
      <a-form-item label="描述"><a-textarea v-model:value="editForm.description" :rows="2" /></a-form-item>
      <a-alert type="info" :closable="false" style="margin-bottom:8px;"
        message="写作风格分三层，生成时如何注入"
        description="① 作家文风特征 与 ② 自定义提示词 互斥，只会注入其一（有文风特征时优先用文风，自定义提示词不生效）；③ 维度配置默认作为基础底色注入，可在下方开关关闭。" />
      <div class="dim-section-head">
        <span class="dim-section-title">③ 维度配置（基础底色）</span>
        <a-tooltip title="关闭后，生成时只注入①或②，不再注入维度配置">
          <a-switch v-model:checked="editForm.config.disable_dimensions" size="small" />
        </a-tooltip>
        <span class="dim-section-hint" :class="{ off: editForm.config.disable_dimensions }">
          {{ editForm.config.disable_dimensions ? '已关闭（不注入维度配置）' : '已开启（作为底色注入）' }}
        </span>
      </div>
      <div v-for="(opts, key) in optionGroups" :key="key" class="dim-row">
        <span class="dim-row-label">{{ labels[key] }}<a-tooltip v-if="isMulti(key)" title="可多选"><span class="dim-multi-hint">多选</span></a-tooltip></span>
        <div class="dim-row-opts">
          <!-- 多选维度：按钮块（手动管理选中态，视觉与单选按钮一致） -->
          <button
            v-if="isMulti(key)" v-for="o in opts" :key="o" type="button"
            class="seg-btn" :class="{ active: isPicked(key, o) }"
            @click="togglePick(key, o)"
          >{{ o }}</button>
          <!-- 单选维度：实心按钮组 -->
          <a-radio-group v-if="!isMulti(key)" v-model:value="editForm.config[key]" size="small" button-style="solid" class="seg-radio">
            <a-radio-button v-for="o in opts" :key="o" :value="o">{{ o }}</a-radio-button>
          </a-radio-group>
        </div>
      </div>
      <a-divider orientation="left">② 自定义提示词（自由文字指令 · 与①互斥）</a-divider>
      <a-alert :type="hasStyleTraits ? 'warning' : 'info'" show-icon :closable="false" style="margin-bottom:10px;"
        :message="hasStyleTraits ? '当前已提炼文风特征，此项不会生效（与①互斥，文风优先）' : '直接写给 AI 的写作风格指令；留空则不注入'" />
      <a-textarea
        v-model:value="editForm.custom_prompt"
        :rows="6"
        placeholder="例如：多用短句和反问，对话占比高，战斗场面要有画面感和冲击力；避免说教式心理独白，角色情绪通过动作和神态展现……"
      />

      <a-divider orientation="left">① 作家文风模仿（最高优先级 · 仿写准则）</a-divider>
      <a-alert type="info" show-icon :closable="false" style="margin-bottom:10px;"
        message="粘贴目标作家（如鲁迅、余华、金庸）的原文片段，AI 会自动提炼出句式/用词/意象/节奏等可操作的文风特征。提炼出的特征是最高优先级的仿写准则，与下面两层冲突时一律以它为准。" />
      <a-form-item label="作家名（可选）">
        <a-input v-model:value="editForm.author_name" placeholder="如：鲁迅" />
      </a-form-item>
      <a-form-item label="范文（粘贴该作家的原文片段）">
        <a-textarea
          v-model:value="editForm.reference_text"
          :rows="6"
          placeholder="粘贴 1~3 段该作家的代表性原文。范文越典型、越接近你想要的笔法，提炼出的特征越准。建议 300~2000 字。"
        />
      </a-form-item>
      <div style="margin-bottom: 12px;">
        <a-button type="primary" ghost :loading="analyzeLoading" @click="onAnalyze">
          <template #icon><span>🔍</span></template>
          AI 提炼文风特征
        </a-button>
        <span style="margin-left:10px; color:#8C8C8C; font-size:12px;">
          点击后会先保存风格，再调用 AI 分析范文（约 10~30 秒）
        </span>
      </div>
      <!-- 提炼结果展示 -->
      <div v-if="Object.keys(editForm.style_traits).length" class="traits-box">
        <div class="traits-title">✨ 已提炼的文风特征（生成时将作为仿写准则）</div>
        <div v-for="(val, key) in editForm.style_traits" :key="key" class="trait-item">
          <span class="trait-key">{{ traitLabels[key] || key }}</span>
          <span class="trait-val">{{ val }}</span>
        </div>
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
.is-default { border-color: #52A569; box-shadow: 0 0 0 1px #52A56940; }
.custom-prompt-box { margin: 10px 0; padding: 8px 10px; background: #F0F5F5; border-radius: 6px; border-left: 3px solid #4D8088; }
.custom-prompt-label { font-size: 11px; color: #4D8088; font-weight: 600; }
.custom-prompt-text { font-size: 12px; color: #595959; margin-top: 4px; white-space: pre-wrap; max-height: 60px; overflow: hidden; }
.dim-row { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 14px; }
.dim-row-label { font-size: 13px; color: #595959; width: 72px; min-width: 72px; flex-shrink: 0; display: flex; align-items: center; gap: 4px; padding-top: 3px; }
.dim-row-opts { flex: 1; min-width: 0; display: flex; flex-wrap: wrap; row-gap: 8px; align-items: center; }
.dim-section-head { display: flex; align-items: center; gap: 10px; margin: 16px 0 12px; }
.dim-section-title { font-size: 13px; color: #595959; font-weight: 600; }
.dim-section-hint { font-size: 12px; color: #8C8C8C; }
.dim-section-hint.off { color: #C75B5B; }
.dim-multi-hint { font-size: 10px; color: #4D8088; background: #EAF0F1; border-radius: 3px; padding: 0 4px; line-height: 16px; }
/* 多选按钮块：视觉与单选 a-radio-button(small, solid) 对齐 */
.seg-radio { display: inline-flex; flex-wrap: wrap; row-gap: 8px; }
.seg-btn {
  appearance: none; -webkit-appearance: none;
  border: 1px solid #d9d9d9; background: #fff; color: #595959;
  height: 24px; padding: 0 12px; margin-right: 8px; cursor: pointer;
  font-size: 13px; line-height: 22px; transition: all .2s;
  border-radius: 6px;
}
.seg-btn:hover { color: #4D8088; border-color: #4D8088; position: relative; z-index: 1; }
.seg-btn.active {
  background: #4D8088; border-color: #4D8088; color: #fff; position: relative; z-index: 2;
}
.traits-box { margin-top: 4px; padding: 10px 12px; background: #F5F0FA; border-radius: 8px; border-left: 3px solid #722ED1; }
.traits-title { font-size: 12px; color: #722ED1; font-weight: 600; margin-bottom: 8px; }
.trait-item { display: flex; gap: 8px; margin-bottom: 8px; font-size: 12px; line-height: 1.6; }
.trait-key { flex: 0 0 90px; color: #8C8C8C; font-weight: 600; }
.trait-val { flex: 1; color: #595959; white-space: pre-wrap; }
</style>
