<script setup lang="ts">
// 首页 = 落地页（landing 布局，无侧边栏）。内容静态，无需后端。
definePageMeta({ layout: 'landing' })
useHead({ title: '墨语 — AI 网文创作平台' })
</script>

<template>
  <nav class="landing-nav">
    <div class="landing-nav-brand">
      <div class="sidebar-brand-logo">M</div>
      <span>墨语</span>
    </div>
    <div class="landing-nav-links">
      <NuxtLink to="/login">登录</NuxtLink>
      <NuxtLink to="/dashboard">
        <a-button type="primary">开始创作</a-button>
      </NuxtLink>
    </div>
  </nav>

  <section class="hero">
    <h1 class="hero-title">让 AI 成为你最得力的创作伙伴</h1>
    <p class="hero-subtitle">从世界观构建到逐章润色，墨语 覆盖网文创作全流程</p>
    <div class="hero-actions">
      <NuxtLink to="/dashboard">
        <a-button type="primary" size="large">立即开始</a-button>
      </NuxtLink>
      <NuxtLink to="/about">
        <a-button size="large">了解更多</a-button>
      </NuxtLink>
    </div>
  </section>

  <section class="features">
    <h2 class="features-title">核心功能</h2>
    <div class="features-grid">
      <a-card hoverable>
        <div class="feature-icon">📋</div>
        <h3>故事大纲</h3>
        <p>AI 辅助生成章节大纲，理清主线与支线</p>
      </a-card>
      <a-card hoverable>
        <div class="feature-icon">📝</div>
        <h3>章节创作</h3>
        <p>逐章撰写、润色、续写，保持风格统一</p>
      </a-card>
      <a-card hoverable>
        <div class="feature-icon">👤</div>
        <h3>角色管理</h3>
        <p>建立角色档案，设定关系网与成长弧线</p>
      </a-card>
      <a-card hoverable>
        <div class="feature-icon">🌍</div>
        <h3>世界设定</h3>
        <p>构建完整世界观，时间线与地理设定一目了然</p>
      </a-card>
    </div>
  </section>

  <footer class="landing-footer"><p>© 2026 墨语 · AI 网文创作平台</p></footer>
</template>

<style scoped>
.landing-nav { display:flex; align-items:center; justify-content:space-between; padding:16px 40px; background:#fff; border-bottom:1px solid var(--color-border); position:sticky; top:0; z-index:100; }
.landing-nav-brand { display:flex; align-items:center; gap:10px; font-weight:700; font-size:18px; }
.landing-nav-links { display:flex; align-items:center; gap:20px; }
.landing-nav-links a { text-decoration:none; font-size:14px; }
.hero { text-align:center; padding:80px 20px 60px; max-width:800px; margin:0 auto; }
.hero-title { font-size:var(--text-hero); font-weight:800; margin-bottom:20px; }
.hero-subtitle { font-size:var(--text-xl); color:var(--color-fg-secondary); margin-bottom:36px; line-height:var(--line-height-relaxed); }
.hero-actions { display:flex; gap:16px; justify-content:center; }
.features { max-width:1000px; margin:0 auto; padding:40px 20px 80px; }
.features-title { text-align:center; font-size:var(--text-3xl); margin-bottom:40px; }
.features-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:24px; }
.feature-icon { font-size:36px; margin-bottom:12px; text-align:center; }
.features-grid h3 { font-size:var(--text-lg); margin-bottom:8px; text-align:center; }
.features-grid p { font-size:var(--text-sm); color:var(--color-fg-secondary); line-height:var(--line-height-normal); text-align:center; }
.landing-footer { text-align:center; padding:24px; border-top:1px solid var(--color-border); color:var(--color-fg-muted); font-size:var(--text-sm); }
@media (max-width:768px) { .features-grid{grid-template-columns:repeat(2,1fr);} .hero-title{font-size:var(--text-3xl);} }
</style>
