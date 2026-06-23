// Nuxt 3 SSR 配置
export default defineNuxtConfig({
  compatibilityDate: '2024-11-01',
  devtools: { enabled: false },

  ssr: true,

  runtimeConfig: {
    apiBase: process.env.NUXT_API_BASE || 'http://localhost:8000',
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_BASE || 'http://localhost:8000',
    },
  },

  app: {
    head: {
      htmlAttrs: { lang: 'zh-CN' },
      charset: 'utf-8',
      viewport: 'width=device-width, initial-scale=1',
      title: '墨语',
      meta: [{ name: 'description', content: '墨语 — AI 网文创作平台' }],
    },
  },

  css: [
    'ant-design-vue/dist/reset.css',
    '@/assets/css/tokens.css',
    '@/assets/css/base.css',
    '@/assets/css/layout.css',
    '@/assets/css/components.css',
    // Vue Flow 样式（全局引入，避免 scoped 作用域导致图谱节点/边不可见）
    '@vue-flow/core/dist/style.css',
    '@vue-flow/core/dist/theme-default.css',
    '@vue-flow/controls/dist/style.css',
    '@vue-flow/minimap/dist/style.css',
  ],

  build: {
    transpile: ['ant-design-vue', '@ant-design/icons-vue', '@vue-flow/core', '@vue-flow/background', '@vue-flow/controls', '@vue-flow/minimap'],
  },

  vite: {
    optimizeDeps: {
      include: [
        'ant-design-vue',
        '@ant-design/icons-vue',
        'dayjs',
        'dayjs/plugin/advancedFormat',
        'dayjs/plugin/customParseFormat',
        'dayjs/plugin/weekday',
        'dayjs/plugin/localeData',
        'dayjs/plugin/weekOfYear',
        'dayjs/plugin/weekYear',
        'dayjs/plugin/quarterOfYear',
      ],
    },
    ssr: {
      noExternal: ['ant-design-vue', '@ant-design/icons-vue', 'dayjs'],
    },
  },

  typescript: { strict: false },
})
