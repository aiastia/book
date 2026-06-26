// Nuxt 3 SSR 配置
export default defineNuxtConfig({
  compatibilityDate: '2024-11-01',
  devtools: { enabled: false },

  ssr: true,

  runtimeConfig: {
    // Nuxt 自动从 .env 读取同名变量，这里设默认值
    apiBase: 'http://localhost:8000',
    public: {
      apiBase: 'http://localhost:8000',
    },
  },

  app: {
    head: {
      htmlAttrs: { lang: 'zh-CN' },
      charset: 'utf-8',
      viewport: 'width=device-width, initial-scale=1',
      title: '墨语',
      meta: [{ name: 'description', content: '墨语 — AI 网文创作平台' }],
      script: [
        // 在 Vue 初始化前拦截 console.warn，抑制 <Suspense> 实验性警告
        { innerHTML: '(function(){var _w=console.warn;console.warn=function(){if(typeof arguments[0]==="string"&&arguments[0].indexOf("<Suspense>")!==-1)return;_w.apply(console,arguments)}})()' },
      ],
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
    build: {
      // 手动拆包：大依赖独立成 chunk，利用浏览器缓存
      rollupOptions: {
        output: {
          manualChunks: {
            'antd': ['ant-design-vue', '@ant-design/icons-vue'],
            'vue-flow': ['@vue-flow/core', '@vue-flow/background', '@vue-flow/controls', '@vue-flow/minimap'],
          },
        },
      },
    },
  },

  typescript: { strict: false },
})
