/**
 * 客户端插件：hydration 完成后自动刷新空数据的 asyncData 条目。
 *
 * 背景：Nuxt 4 的 useAsyncData 在 hydration 时，如果 SSR payload 中已有数据
 *（包括 null 或 error），客户端不会重新请求。但如果 SSR 请求失败或返回 null，
 * 页面会一直显示空数据。此插件在 hydration 完成后检查所有 asyncData 条目，
 * 对 data 为 null/undefined 的条目自动触发一次客户端请求。
 */
export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.hook('app:suspense:resolve', () => {
    // 收集需要刷新的 key（避免在遍历中修改）
    const keysToRefresh: string[] = []

    for (const key in nuxtApp._asyncData) {
      const entry = nuxtApp._asyncData[key]
      // 跳过未初始化或已有有效数据的条目
      if (!entry?._init) continue
      // data 为 null 或 undefined 才需要刷新（空数组 [] 是合法数据，不刷新）
      if (entry.data?.value != null) continue
      // 正在请求中的也不刷新
      if (entry.status?.value === 'pending') continue

      keysToRefresh.push(key)
    }

    if (keysToRefresh.length > 0) {
      // 延迟到 nextTick，避免与 hydration 过程冲突
      nextTick(() => {
        for (const key of keysToRefresh) {
          const entry = nuxtApp._asyncData[key]
          if (entry?._init) {
            entry.execute({ cause: 'refresh:hook', dedupe: 'cancel' }).catch(() => {
              // 静默处理刷新失败（原始 SSR 失败信息已在 payload 中）
            })
          }
        }
      })
    }
  })
})
