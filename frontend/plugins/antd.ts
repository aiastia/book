// Ant Design Vue 插件 — SSR + 客户端双端注册
// 修复 Ant Design 4.x CSS-in-JS 的 SSR 水合不匹配
// 原理：共享 createCache() 实例，StyleProvider 确保两端 CSS hash 一致
import Antd, { createCache, extractStyle } from 'ant-design-vue'

// 尽早拦截 console.warn：Vue 的 <Suspense> 实验性警告在模块初始化阶段触发
if (import.meta.client) {
  const rawWarn = console.warn
  console.warn = (...args: any[]) => {
    const msg = String(args[0] || '')
    if (msg.includes('<Suspense> is an experimental feature')) return
    rawWarn.apply(console, args)
  }
}

export default defineNuxtPlugin((nuxtApp) => {
  const cache = createCache()

  // 提供给 app.vue 的 <a-style-provider :cache="..."> 使用
  nuxtApp.provide('antdCache', cache)

  nuxtApp.vueApp.use(Antd)

  // SSR：渲染完成后提取 antd 样式并注入到页面 <head>
  if (import.meta.server) {
    nuxtApp.hook('app:rendered', () => {
      const styleText = extractStyle(cache, true)
      if (styleText && nuxtApp.ssrContext?.head) {
        ;(nuxtApp.ssrContext.head as any[]).push({
          style: [{ key: 'antd-cssinjs', innerHTML: styleText }],
        })
      }
    })
  }
})
