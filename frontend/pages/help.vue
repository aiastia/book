<script setup lang="ts">
import { useProject } from '~/composables/useProject'
useHead({ title: '帮助中心 — 墨语' })
const { projectUrl } = useProject()
const faqs = [
  { q: '如何创建第一本小说？', a: '登录后进入「我的小说」→ 点击「新建小说」→ 填写书名与简介即可。' },
  { q: 'AI 生成章节如何使用？', a: '在「章节创作」页面选择章节 → 点击「AI 续写」→ 等待生成结果后可编辑修改。' },
  { q: '如何管理多个角色？', a: '在「角色管理」页面可以为每个角色建立档案、关系网与出场记录。' },
  { q: '拆书导入支持哪些格式？', a: '目前支持 TXT（GBK/UTF-8）、EPUB、Markdown 三种格式。' },
]
const guides = computed(() => [
  { icon: '🚀', title: '快速开始', desc: '5 分钟上手 墨语', to: projectUrl('/dashboard') },
  { icon: '📖', title: '创作指南', desc: '从大纲到成稿的完整流程', to: projectUrl('/outline') },
  { icon: '🔧', title: 'AI 配置', desc: '如何接入与调优 AI 模型', to: '/ai-settings' },
])

const activeCollapse = ref<string[]>([])
</script>
<template>
  <div class="help">
    <h1>帮助中心</h1>
    <p class="help-sub">在这里找到 墨语 的使用答案</p>
    <div class="guide-grid">
      <NuxtLink v-for="g in guides" :key="g.title" :to="g.to">
        <a-card hoverable class="guide-card">
          <div class="guide-icon">{{ g.icon }}</div>
          <div class="guide-title">{{ g.title }}</div>
          <div class="guide-desc">{{ g.desc }}</div>
        </a-card>
      </NuxtLink>
    </div>
    <h2 class="faq-title">常见问题</h2>
    <a-collapse v-model:activeKey="activeCollapse" class="faq-collapse">
      <a-collapse-panel v-for="(f, i) in faqs" :key="String(i)" :header="f.q">
        <p>{{ f.a }}</p>
      </a-collapse-panel>
    </a-collapse>
    <div class="help-contact">没有找到答案？<NuxtLink to="/about">联系我们 →</NuxtLink></div>
  </div>
</template>
<style scoped>
.help{max-width:760px;margin:0 auto;padding:24px 20px 40px;}
.help h1{font-size:var(--text-3xl);margin-bottom:8px;}
.help-sub{color:var(--color-fg-secondary);margin-bottom:40px;}
.guide-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:48px;}
.guide-card{text-align:center;cursor:pointer;}
.guide-icon{font-size:28px;margin-bottom:8px;}
.guide-title{font-size:var(--text-md);font-weight:600;margin-bottom:4px;}
.guide-desc{font-size:var(--text-sm);color:var(--color-fg-secondary);}
.faq-title{font-size:var(--text-xl);margin-bottom:16px;}
.faq-collapse{margin-bottom:20px;}
.faq-collapse p{font-size:var(--text-sm);color:var(--color-fg-secondary);line-height:1.6;}
.help-contact{text-align:center;margin-top:40px;font-size:var(--text-sm);color:var(--color-fg-secondary);}
.help-contact a{color:var(--color-primary);text-decoration:none;}
@media (max-width:768px){.guide-grid{grid-template-columns:1fr;}}
</style>
