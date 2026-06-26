<script setup lang="ts">
// App 后台外壳：固定侧栏 + 主色顶栏 + 内容白卡
// 侧栏折叠状态同步到 main-content 和 header 的 margin/left
const collapsed = ref(false)
const route = useRoute()

if (import.meta.client) {
  onMounted(() => {
    const saved = localStorage.getItem('moyu_sidebar_collapsed')
    if (saved !== null) collapsed.value = saved === '1'

    // 监听 localStorage 变化（跨标签页同步）
    window.addEventListener('storage', () => {
      collapsed.value = localStorage.getItem('moyu_sidebar_collapsed') === '1'
    })
    // 侧栏 toggle 通知
    window.addEventListener('moyu-sidebar-toggle', (e: any) => {
      collapsed.value = e.detail
    })
  })
}

// 顶栏标题（根据路由推断）
const headerTitle = computed(() => {
  const map: Record<string, string> = {
    '/dashboard': '工作台', '/worldview': '世界设定', '/characters': '角色设定',
    '/relations': '关系图谱', '/organizations': '组织与势力', '/outline': '故事大纲',
    '/chapters': '故事章节', '/analysis': '剧情分析', '/foreshadows': '伏笔管理',
    '/memories': '故事记忆', '/items': '物品道具', '/locations': '地点地图', '/chapter-reader': '章节阅读',
    '/admin/users': '用户管理', '/admin/system': '系统设置',
    '/writing-style': '写作风格', '/inspire': '灵感模式', '/books': '我的书架',
  }
  const path = route.path.replace(/\.html$/, '').replace(/\/$/, '') || '/'
  return map[path] || '墨语'
})
</script>

<template>
  <div class="app-layout">
    <AppSidebar />
    <div class="main-content" :class="{ 'sidebar-collapsed': collapsed }">
      <!-- 主色顶栏 -->
      <header class="app-header" :class="{ 'sidebar-collapsed': collapsed }">
        <div class="app-header-title">{{ headerTitle }}</div>
        <div class="app-header-actions">
          <slot name="header-actions" />
        </div>
      </header>
      <!-- 内容白卡 -->
      <div class="page-content">
        <div class="content-card">
          <slot />
        </div>
      </div>
    </div>
    <ClientOnly>
      <InitTaskFloat />
    </ClientOnly>
  </div>
</template>
