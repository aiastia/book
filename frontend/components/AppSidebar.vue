<script setup lang="ts">
// 侧边栏：主色 Logo 区 + 折叠 + 分组菜单 + 项目上下文 + 用户
const { nav, currentPath, adminNav, showAdminEntry } = useNavigation()
const { currentProjectInfo } = useProject()

const collapsed = ref(false)
if (import.meta.client) {
  const saved = localStorage.getItem('moyu_sidebar_collapsed')
  if (saved !== null) collapsed.value = saved === '1'
}
function toggleCollapse() {
  collapsed.value = !collapsed.value
  if (import.meta.client) {
    localStorage.setItem('moyu_sidebar_collapsed', collapsed.value ? '1' : '0')
    // 通知 default.vue 更新 margin
    window.dispatchEvent(new CustomEvent('moyu-sidebar-toggle', { detail: collapsed.value }))
  }
}

const groupedNav = computed(() => {
  const groups = [{ title: '导航', items: nav.value }]
  // 管理员入口（非管理页面时，在底部显示）
  if (showAdminEntry.value && !currentPath.value.startsWith('/admin')) {
    groups.push({ title: '管理', items: adminNav.value })
  }
  return groups
})
</script>

<template>
  <aside class="sidebar" :class="{ collapsed }">
    <div class="sidebar-brand">
      <div class="sidebar-brand-logo">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M4 19.5A2.5 2.5 0 016.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" />
        </svg>
      </div>
      <span class="sidebar-brand-text">墨语 AI 小说</span>
      <button class="sidebar-brand-collapse" @click="toggleCollapse">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
          <polyline v-if="!collapsed" points="15 18 9 12 15 6" /><polyline v-else points="9 18 15 12 9 6" />
        </svg>
      </button>
    </div>

    <div v-if="currentProjectInfo" class="sidebar-project">
      <div class="sidebar-project-label">当前作品</div>
      <div class="sidebar-project-name"><span>📖</span>{{ currentProjectInfo.title }}</div>
    </div>

    <nav class="sidebar-nav">
      <template v-for="group in groupedNav" :key="group.title">
        <div class="sidebar-group-title">{{ group.title }}</div>
        <SidebarNavItem
          v-for="item in group.items"
          :key="item.to"
          :to="item.to"
          :icon="item.icon"
          :active="currentPath === item.to"
          :collapsed="collapsed"
        >{{ collapsed ? '' : item.label }}</SidebarNavItem>
      </template>
    </nav>

    <ClientOnly>
      <SidebarUser />
    </ClientOnly>
  </aside>
</template>
