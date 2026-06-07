// 客户端路由同步插件：从 URL 的 ?pid= 参数恢复项目上下文
// 刷新页面时确保项目 ID 不丢失
export default defineNuxtPlugin(() => {
  const route = useRoute()
  const { syncFromQuery } = useProject()

  // 首次加载时同步
  syncFromQuery()

  // 每次路由变化时同步
  watch(() => route.fullPath, () => {
    nextTick(() => syncFromQuery())
  })
})
