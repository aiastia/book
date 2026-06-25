// Ant Design Vue 插件 — SSR + 客户端双端注册
import Antd from 'ant-design-vue'

// 尽早拦截 console.warn，捕获 Vue 初始化阶段的 Suspense 警告（早于 Nuxt 插件执行）
if (import.meta.client) {
  const rawWarn = console.warn
  console.warn = function (...args: any[]) {
    const msg = args.length > 0 ? String(args[0]) : ''
    // Nuxt 内部 <Suspense> 实验性警告（模块初始化阶段触发）
    if (msg.includes('<Suspense> is an experimental feature')) return
    rawWarn.apply(console, args)
  }
}

export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.vueApp.use(Antd)

  if (import.meta.client) {
    const prev = nuxtApp.vueApp.config.warnHandler
    nuxtApp.vueApp.config.warnHandler = (msg: string, instance: any, trace: string) => {
      if (typeof msg === 'string') {
        // Suspense 双保险
        if (msg.includes('<Suspense>')) return
        // Ant Design 组件以 A 开头（AEmpty, ASkeleton, AStatistic, ACard, ATag 等）
        const isAntdTrace = typeof trace === 'string' && /\bA[A-Z]\w+/.test(trace)
        if (isAntdTrace) return
        // Ant Design 已知 SSR class 模式
        if (msg.includes('Hydration') && (
          msg.includes('ant-') ||           // ant-empty, ant-statistic, etc.
          msg.includes('css-dev-only') ||   // Ant Design 的 hash class
          msg.includes('class="null"')      // Ant Design SSR class 为 null
        )) return
      }
      if (prev) prev(msg, instance, trace)
    }
  }
})
