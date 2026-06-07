// Ant Design Vue 插件 — SSR + 客户端双端注册
import Antd from 'ant-design-vue'

export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.vueApp.use(Antd)
})
