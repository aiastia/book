<script setup lang="ts">
// 物品/道具管理：分类切换 + 卡片网格 + AI 生成 + CRUD
import { API } from '~/composables/api'
import { useProject } from '~/composables/useProject'
useHead({ title: '物品道具 — 墨语' })
const { currentProjectId } = useProject()
if (!currentProjectId.value) await navigateTo('/books')
const msg = useMessage()
const { data: items, refresh: refreshItems } = await useFetch<any>(() => `/projects/${currentProjectId.value}/items`)
const { data: characters, refresh: refreshChars } = await useFetch<any>(() => `/projects/${currentProjectId.value}/characters`)

const generating = ref(false)
const showAdd = ref(false)
const showGen = ref(false)
const genCount = ref(6)
const genCategory = ref('')
const genReq = ref('')
const editing = ref<any>(null)
const form = reactive({
  id: 0, name: '', category: '装备', rarity: 'common', item_type: '',
  description: '', attributes: {} as any, owner_name: '', obtained_chapter: null as number | null,
  status: 'in_use', is_key_item: 0, quantity: 1,
})

// 分类筛选
const filterCategory = ref('')
const filteredItems = computed(() => {
  const list = items.value || []
  if (!filterCategory.value) return list
  return list.filter((i: any) => i.category === filterCategory.value)
})

const categoryList = ['装备', '消耗', '关键道具', '材料', '货币', '其他']
const rarityMeta: Record<string, { label: string; color: string }> = {
  common: { label: '普通', color: '#8C8C8C' },
  uncommon: { label: '精良', color: '#52A569' },
  rare: { label: '稀有', color: '#4D8088' },
  epic: { label: '史诗', color: '#9B59B6' },
  legendary: { label: '传说', color: '#D49A4E' },
  mythic: { label: '神话', color: '#E74C3C' },
}
const statusMeta: Record<string, { label: string; color: string }> = {
  in_use: { label: '使用中', color: 'success' },
  stored: { label: '存放', color: 'default' },
  consumed: { label: '已消耗', color: 'warning' },
  lost: { label: '遗失', color: 'error' },
  destroyed: { label: '已毁', color: 'error' },
}

async function onGenerate() {
  genCategory.value = filterCategory.value
  showGen.value = true
}
async function doGenerate() {
  generating.value = true
  try {
    const r = await API.item.generate({ count: genCount.value, category: genCategory.value, user_prompt: genReq.value })
    await refreshItems()
    showGen.value = false
    msg.success(`生成 ${r.count} 个物品`)
  } catch (e: any) { msg.error('生成失败：' + formatError(e)) }
  finally { generating.value = false }
}
function openAdd() {
  editing.value = null
  Object.assign(form, { id: 0, name: '', category: '装备', rarity: 'common', item_type: '', description: '', attributes: {}, owner_name: '', obtained_chapter: null, status: 'in_use', is_key_item: 0, quantity: 1 })
  showAdd.value = true
}
function openEdit(i: any) {
  editing.value = i
  Object.assign(form, { ...i, attributes: i.attributes || {} })
  showAdd.value = true
}
async function onSave() {
  if (!form.name.trim()) return
  try {
    if (editing.value) await API.item.update(form.id, { ...form })
    else await API.item.create({ ...form })
    showAdd.value = false
    await refreshItems()
    msg.success(editing.value ? '已更新' : '已添加')
  } catch (e: any) { msg.error('保存失败：' + formatError(e)) }
}
async function onDelete(id: number) {
  if (!await msg.confirm('确认删除？')) return
  try { await API.item.delete(id); await refreshItems(); msg.success('已删除') }
  catch (e: any) { msg.error('删除失败：' + formatError(e)) }
}
</script>

<template>
  <PageHeader title="物品道具">
    <template #actions>
      <a-button @click="openAdd">+ 添加物品</a-button>
      <a-button type="primary" :loading="generating" @click="onGenerate">{{ generating ? '生成中…' : ((items||[]).length ? '➕ 追加生成' : 'AI 生成物品') }}</a-button>
    </template>
  </PageHeader>

  <div class="page-content">
    <div class="filter-bar">
      <a-checkable-tag :checked="!filterCategory" @change="filterCategory = ''">全部</a-checkable-tag>
      <a-checkable-tag v-for="c in categoryList" :key="c" :checked="filterCategory === c" @change="filterCategory = c">{{ c }}</a-checkable-tag>
    </div>

    <div v-if="filteredItems.length" class="item-grid">
      <a-card v-for="i in filteredItems" :key="i.id" hoverable class="item-card" :class="{ 'key-item': i.is_key_item }">
        <div class="card-head">
          <span class="rarity-dot" :style="{ background: rarityMeta[i.rarity]?.color || '#8C8C8C' }"></span>
          <span class="item-name">{{ i.name }}</span>
          <a-tag v-if="i.is_key_item" color="red" size="small">关键</a-tag>
          <div class="head-actions">
            <a-button type="link" size="small" @click="openEdit(i)">编辑</a-button>
            <a-button type="link" danger size="small" @click="onDelete(i.id)">删除</a-button>
          </div>
        </div>
        <div class="card-meta">
          <a-tag size="small" :style="{ color: rarityMeta[i.rarity]?.color, borderColor: rarityMeta[i.rarity]?.color }">{{ rarityMeta[i.rarity]?.label || i.rarity }}</a-tag>
          <a-tag size="small">{{ i.category }}</a-tag>
          <a-tag v-if="i.item_type" size="small">{{ i.item_type }}</a-tag>
          <a-tag size="small" :color="statusMeta[i.status]?.color">{{ statusMeta[i.status]?.label || i.status }}</a-tag>
          <span v-if="i.quantity > 1" class="qty">×{{ i.quantity }}</span>
        </div>
        <div v-if="i.description" class="item-desc">{{ i.description }}</div>
        <div v-if="i.attributes && Object.keys(i.attributes).length" class="item-attrs">
          <span v-for="(v, k) in i.attributes" :key="k" class="attr-chip">{{ k }}: {{ v }}</span>
        </div>
        <div class="card-foot">
          <span v-if="i.owner_name" class="owner">持有者：{{ i.owner_name }}</span>
          <span v-if="i.obtained_chapter" class="chap">第 {{ i.obtained_chapter }} 章获得</span>
        </div>
      </a-card>
    </div>
    <a-empty v-else description="暂无物品，点击「AI 生成物品」" />

    <a-modal v-model:open="showAdd" :title="editing ? '编辑物品' : '添加物品'" width="560px">
      <a-form layout="vertical">
        <div class="form-row2">
          <a-form-item label="名称"><a-input v-model:value="form.name" /></a-form-item>
          <a-form-item label="数量"><a-input-number v-model:value="form.quantity" :min="1" style="width:100%" /></a-form-item>
        </div>
        <div class="form-row3">
          <a-form-item label="分类">
            <a-select v-model:value="form.category">
              <a-select-option v-for="c in categoryList" :key="c" :value="c">{{ c }}</a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="稀有度">
            <a-select v-model:value="form.rarity">
              <a-select-option v-for="(m, k) in rarityMeta" :key="k" :value="k">{{ m.label }}</a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="状态">
            <a-select v-model:value="form.status">
              <a-select-option v-for="(m, k) in statusMeta" :key="k" :value="k">{{ m.label }}</a-select-option>
            </a-select>
          </a-form-item>
        </div>
        <a-form-item label="细分类型"><a-input v-model:value="form.item_type" placeholder="武器/防具/丹药/功法..." /></a-form-item>
        <a-form-item label="描述"><a-textarea v-model:value="form.description" :rows="3" /></a-form-item>
        <div class="form-row2">
          <a-form-item label="持有者">
            <a-select v-model:value="form.owner_name" show-search allow-clear placeholder="选择角色">
              <a-select-option value="">无主</a-select-option>
              <a-select-option v-for="c in (characters || [])" :key="c.name" :value="c.name">{{ c.name }}({{ c.role }})</a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="获得章节"><a-input-number v-model:value="form.obtained_chapter" :min="1" style="width:100%" /></a-form-item>
        </div>
        <a-form-item>
          <a-checkbox v-model:checked="form.is_key_item" :true-value="1" :false-value="0">关键剧情道具（影响主线）</a-checkbox>
        </a-form-item>
      </a-form>
      <template #footer>
        <a-button @click="showAdd = false">取消</a-button>
        <a-button type="primary" @click="onSave">保存</a-button>
      </template>
    </a-modal>

    <!-- AI 生成物品弹窗 -->
    <a-modal v-model:open="showGen" :title="(items||[]).length ? '追加生成物品' : 'AI 生成物品'" width="460px">
      <a-alert
        v-if="(items||[]).length"
        message="已有物品将保留，本次为追加生成（不覆盖）。AI 会避开已有的物品。"
        type="info" show-icon :closable="false" style="margin-bottom:12px"
      />
      <a-form layout="vertical">
        <a-form-item label="生成数量">
          <a-input-number v-model:value="genCount" :min="1" :max="10" style="width:100%" />
        </a-form-item>
        <a-form-item label="物品分类">
          <a-select v-model:value="genCategory" allow-clear placeholder="全部分类">
            <a-select-option value="">全部分类</a-select-option>
            <a-select-option v-for="c in categoryList" :key="c" :value="c">{{ c }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="额外需求（可选）">
          <a-textarea v-model:value="genReq" :rows="2" placeholder="如：需要几件修仙法宝、需要一些消耗品..." />
        </a-form-item>
      </a-form>
      <template #footer>
        <a-button @click="showGen = false">取消</a-button>
        <a-button type="primary" :loading="generating" @click="doGenerate">{{ generating ? '生成中…' : '开始生成' }}</a-button>
      </template>
    </a-modal>
  </div>
</template>

<style scoped>
.filter-bar { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; }
.item-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 14px; }
.item-card { border-left: 3px solid #8C8C8C !important; transition: border-color .2s; }
.item-card.key-item { border-left-color: #E74C3C !important; }
.card-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.rarity-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.item-name { font-size: 15px; font-weight: 600; flex: 1; }
.head-actions { display: flex; }
.card-meta { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; }
.qty { font-size: 13px; color: #8C8C8C; font-weight: 600; }
.item-desc { font-size: 13px; color: #595959; line-height: 1.6; margin-bottom: 8px; }
.item-attrs { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.attr-chip { font-size: 11px; background: #EAF0F1; color: #4D8088; padding: 2px 8px; border-radius: 4px; }
.card-foot { display: flex; gap: 12px; font-size: 12px; color: #8C8C8C; }
.form-row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.form-row3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
</style>
