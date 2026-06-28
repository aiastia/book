<script setup lang="ts">
import { API } from '~/composables/api'
import { UploadOutlined, LoadingOutlined } from '@ant-design/icons-vue'
useHead({ title: '拆书导入 — 墨语' })
const msg = useMessage()
const { data: imported, refresh } = await useApi<any[]>('/api/imported-books', { key: 'imported-books' })
const uploading = ref(false)
const fileList = ref<any[]>([])

// 拆解流程状态
// parseStep: 0=未开始, 1=配置采样, 2=拆解中, 3=完成
const parseStep = ref(0)
const parseTarget = ref<any>(null)
const parseLoading = ref(false)
const sampleSide = ref<'head' | 'tail'>('head')   // 立项采样方向
const sampleCount = ref(5)                          // 立项采样章数
const outlineChapters = ref(20)                     // 大纲拆解章数
const deconstructResult = ref<any>(null)            // 拆解结果

async function handleUpload(options: any) {
  const file = options.file
  if (!file) return
  uploading.value = true
  try {
    // 读取文件为 base64
    const base64 = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => {
        const result = String(reader.result || '')
        // data:text/plain;base64,xxxx
        const idx = result.indexOf(',')
        resolve(idx >= 0 ? result.slice(idx + 1) : result)
      }
      reader.onerror = () => reject(new Error('读取文件失败'))
      reader.readAsDataURL(file)
    })
    await API.bookImport.upload({ filename: file.name, base64 })
    msg.success('导入成功！已解析章节并入库')
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
    await API.bookImport.delete(b.id)
    msg.success('已删除')
    await refresh()
  } catch { msg.error('删除失败') }
}

// 启动拆解：打开配置弹窗
function startParse(b: any) {
  parseTarget.value = b
  parseStep.value = 1
  deconstructResult.value = null
  // 默认采样不超过该书的章数
  sampleCount.value = Math.min(5, b.total_chapters || b.chapters || 5) || 5
}

// 确认配置 → 执行一键拆解
async function onDeconstruct() {
  if (!parseTarget.value) return
  parseLoading.value = true
  parseStep.value = 2
  try {
    const res = await API.bookImport.deconstruct(parseTarget.value.id, {
      sample_side: sampleSide.value,
      sample_count: sampleCount.value,
      outline_chapters: outlineChapters.value,
    })
    deconstructResult.value = res
    parseStep.value = 3
    msg.success(`拆解完成！已生成 ${res.outline_count} 章大纲`)
    await refresh()
  } catch (e: any) {
    msg.error('拆解失败：' + formatError(e))
    parseStep.value = 1
  } finally {
    parseLoading.value = false
  }
}

function closeParse() {
  parseStep.value = 0
  parseTarget.value = null
  deconstructResult.value = null
}

// ===== 直接 TXT 导入（解析 + 批量落库，不走 AI）=====
const directMode = ref(false)
const directText = ref('')
const directParsing = ref(false)
const directResult = ref<{ chapters: any[]; stats: any } | null>(null)
const directTitle = ref('')
const directGenre = ref('')
const directImporting = ref(false)

// 格式要求面板：默认展开，用户可在页面上折叠/展开
const activeFmtPanel = ref<string[]>(['fmt'])

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

    <!-- 格式要求说明（两种模式共用） -->
    <a-collapse v-model:active-key="activeFmtPanel" :bordered="false" ghost style="margin-bottom:16px">
      <a-collapse-panel key="fmt" header="📄 TXT 格式要求（点击收起/展开）">
        <div class="fmt-help">
          <p class="fmt-line fmt-good">✅ <b>最佳格式</b>：每章以「第X章」独占一行开头，识别最准。</p>
          <pre class="fmt-example">第一章 山村少年

正文内容……

第二章 初入仙门

正文内容……</pre>
          <p class="fmt-line">识别的标题：<code>第X章/卷/节/回/集/部/篇</code>（中文数字或阿拉伯数字均可）、<code>Chapter N</code>、<code>Chap. 1</code>、纯数字 <code>1.</code></p>
          <p class="fmt-line fmt-warn">⚠️ <b>无「第X章」标记</b>：若有短标题行（前后空行、无句号、含数字或「章/节/回」）也能切；完全没有标记则按约 4000 字机械切章，精度较低。</p>
          <p class="fmt-line fmt-tip">💡 <b>编码</b>：自动识别 UTF-8 / GBK / GB18030 / Big5，无需手动转码。</p>
          <p class="fmt-line fmt-tip">💡 <b>建议</b>：上传后留意「章节标记是否清晰」标记，不清晰请补上「第X章」再重新上传，否则 AI 拆出的大纲对不上真实章节边界。</p>
        </div>
      </a-collapse-panel>
    </a-collapse>

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
        accept=".txt"
        class="upload-area"
      >
        <div class="upload-inner">
          <UploadOutlined style="font-size:48px;color:#c0c4cc;" />
          <div style="font-size:15px;color:#606266;margin-top:12px;">拖拽小说 TXT 到此处，或点击选择</div>
          <div style="font-size:13px;color:#909399;margin-top:6px;">支持 TXT (GBK/UTF-8)，上传后可一键 AI 拆解</div>
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
            <div style="font-size:12px;color:#888;margin-top:4px;">{{ b.total_chapters ?? b.chapters ?? 0 }} 章 · {{ (b.total_chars ?? 0).toLocaleString() }} 字 · {{ b.updated || '' }}</div>
          </div>
          <div style="display:flex;align-items:center;gap:8px;">
            <a-tag :color="b.tag === '已拆解' ? 'success' : 'processing'" size="small">{{ b.tag || '待拆解' }}</a-tag>
            <a-button type="primary" size="small" :disabled="b.tag === '已拆解'" @click="startParse(b)">
              {{ b.tag === '已拆解' ? '已拆解' : 'AI 拆解' }}
            </a-button>
            <a-button size="small" danger @click="onDeleteImport(b)">删除</a-button>
          </div>
        </div>
      </a-card>
    </div>
    <a-empty v-else description="暂无导入记录" :image-style="{ height: '60px' }" />
  </div>

  <!-- AI 拆解弹窗 -->
  <a-modal
    :open="parseStep > 0"
    title="AI 拆解 — 一键生成项目"
    width="560px"
    :footer="null"
    :mask-closable="false"
    @cancel="closeParse"
  >
    <!-- 步骤1: 配置采样 -->
    <div v-if="parseStep === 1">
      <a-alert type="info" show-icon :closable="false" style="margin-bottom:16px">
        <template #message>将基于采样章节反向提炼立项信息，并连续拆解前 {{ outlineChapters }} 章大纲，一次性生成完整项目。</template>
      </a-alert>
      <a-descriptions :column="1" size="small" bordered style="margin-bottom:16px">
        <a-descriptions-item label="书名">{{ parseTarget?.title }}</a-descriptions-item>
        <a-descriptions-item label="总章数">{{ parseTarget?.total_chapters ?? parseTarget?.chapters ?? 0 }} 章</a-descriptions-item>
      </a-descriptions>

      <div style="margin-bottom:16px">
        <div style="font-weight:500;margin-bottom:8px;">① 立项采样（用于提炼简介/题材/视角）</div>
        <a-radio-group v-model:value="sampleSide" button-style="solid">
          <a-radio-button value="head">采样前 {{ sampleCount }} 章（看开头定调）</a-radio-button>
          <a-radio-button value="tail">采样后 {{ sampleCount }} 章（看结局走向）</a-radio-button>
        </a-radio-group>
      </div>

      <div style="margin-bottom:20px">
        <div style="font-weight:500;margin-bottom:8px;">② 大纲深度（连续拆解前 N 章）</div>
        <a-radio-group v-model:value="outlineChapters" button-style="solid">
          <a-radio-button :value="10">前 10 章</a-radio-button>
          <a-radio-button :value="20">前 20 章</a-radio-button>
          <a-radio-button :value="30">前 30 章</a-radio-button>
        </a-radio-group>
        <div style="font-size:12px;color:#909399;margin-top:6px;">章数越多 token 消耗越大。拆解含多批 AI 调用，预计耗时 1-3 分钟。</div>
      </div>

      <div style="display:flex;justify-content:flex-end;gap:8px;">
        <a-button @click="closeParse">取消</a-button>
        <a-button type="primary" @click="onDeconstruct">开始拆解</a-button>
      </div>
    </div>

    <!-- 步骤2: 拆解中 -->
    <div v-if="parseStep === 2" style="text-align:center;padding:30px 20px;">
      <LoadingOutlined :spin="true" style="font-size:28px;color:#4D8088;" />
      <p style="margin-top:14px;color:#666;font-size:15px;">正在拆解「{{ parseTarget?.title }}」…</p>
      <p style="color:#909399;font-size:13px;margin-top:4px;">采样立项 + 拆解前 {{ outlineChapters }} 章大纲，预计 1-3 分钟，请勿关闭</p>
    </div>

    <!-- 步骤3: 完成 -->
    <div v-if="parseStep === 3 && deconstructResult" style="padding:8px 4px;">
      <div style="text-align:center;margin-bottom:16px;">
        <div style="font-size:40px;">✅</div>
        <h3 style="color:#4D8088;margin:8px 0;">拆解完成！</h3>
        <p style="color:#666;font-size:13px;">生成 {{ deconstructResult.outline_count }} 章大纲 · 共 {{ deconstructResult.batches_done }} 批</p>
      </div>
      <a-descriptions bordered :column="1" size="small">
        <a-descriptions-item label="书名">{{ deconstructResult.project_info?.title || parseTarget?.title }}</a-descriptions-item>
        <a-descriptions-item label="题材">{{ deconstructResult.project_info?.genre || '-' }}</a-descriptions-item>
        <a-descriptions-item label="叙事视角">{{ deconstructResult.project_info?.narrative_perspective || '-' }}</a-descriptions-item>
        <a-descriptions-item label="简介">{{ deconstructResult.project_info?.description || '-' }}</a-descriptions-item>
      </a-descriptions>
      <div style="margin-top:16px;display:flex;justify-content:center;gap:8px;">
        <NuxtLink :to="`/outline?pid=${deconstructResult.project_id}`">
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

/* 格式要求面板 */
.fmt-help { font-size: 13px; color: #595959; }
.fmt-line { margin: 6px 0; line-height: 1.7; }
.fmt-line code { background: #F0EDE6; padding: 1px 6px; border-radius: 3px; font-size: 12px; color: #4D8088; }
.fmt-good { color: #389e0d; }
.fmt-warn { color: #d48806; }
.fmt-tip { color: #595959; }
.fmt-example {
  background: #FAFAF7; border: 1px solid #F0EDE6; border-radius: 6px;
  padding: 10px 12px; margin: 8px 0; font-size: 12.5px; color: #595959;
  white-space: pre-wrap; line-height: 1.6;
}
</style>
