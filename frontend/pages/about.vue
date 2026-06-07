<script setup lang="ts">
useHead({ title: '关于我们 — 墨语' })
const features = [
  { icon: '📋', title: '故事大纲', desc: 'AI 辅助生成章节大纲' },
  { icon: '📝', title: '章节创作', desc: '逐章撰写与润色' },
  { icon: '👤', title: '角色管理', desc: '角色档案与关系网' },
  { icon: '🌍', title: '世界设定', desc: '完整世界观构建' },
]
</script>
<template>
  <div class="about">
    <div class="about-hero">
      <div class="about-logo">M</div>
      <h1>墨语</h1>
      <p class="about-tagline">AI 网文创作平台</p>
    </div>
    <p class="about-desc">墨语 致力于用 AI 赋能网络文学创作，从世界观构建、角色设定到逐章撰写与润色，覆盖创作全流程。</p>
    <div class="feature-grid">
      <a-card v-for="f in features" :key="f.title" hoverable>
        <div class="feature-icon">{{ f.icon }}</div>
        <h3>{{ f.title }}</h3>
        <p>{{ f.desc }}</p>
      </a-card>
    </div>
    <div class="about-meta"><p>版本 v1.0.0</p><p>联系我们：support@mumainovel.com</p></div>
  </div>
</template>
<style scoped>
.about{max-width:720px;margin:0 auto;padding:24px 20px 40px;text-align:center;}
.about-hero{margin-bottom:24px;}
.about-logo{width:64px;height:64px;border-radius:14px;background:linear-gradient(135deg,var(--color-primary),var(--color-accent));color:#fff;font-size:32px;font-weight:800;display:flex;align-items:center;justify-content:center;margin:0 auto 16px;}
.about h1{font-size:var(--text-3xl);margin-bottom:4px;}
.about-tagline{color:var(--color-fg-secondary);}
.about-desc{color:var(--color-fg-secondary);line-height:1.7;margin-bottom:40px;}
.feature-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:20px;margin-bottom:40px;}
.feature-icon{font-size:28px;margin-bottom:8px;}
.feature-grid h3{font-size:var(--text-md);margin-bottom:4px;}
.feature-grid p{font-size:var(--text-sm);color:var(--color-fg-secondary);}
.about-meta{font-size:var(--text-sm);color:var(--color-fg-muted);line-height:1.8;}
</style>
