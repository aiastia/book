// Ant Design Vue 插件 — SSR + 客户端双端注册
import Antd from 'ant-design-vue'

export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.vueApp.use(Antd)

  // 抑制 Nuxt 内部使用 <Suspense> 产生的实验性警告（不影响功能）
  if (import.meta.client) {
    const originalWarnHandler = nuxtApp.vueApp.config.warnHandler
    nuxtApp.vueApp.config.warnHandler = (msg: string, instance: any, trace: string) => {
      if (typeof msg === 'string' && msg.includes('<Suspense> is an experimental feature')) {
        return
      }
      if (originalWarnHandler) {
        originalWarnHandler(msg, instance, trace)
      } else {
        console.warn(msg)
      }
    }
  }
})
