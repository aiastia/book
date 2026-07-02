<script setup lang="ts">
// 侧边栏：主色 Logo 区 + 折叠 + 分组菜单 + 项目上下文 + 用户
import { nextTick, onMounted, computed } from 'vue'

const { nav, groupedNav, currentPath, adminNav, showAdminEntry } = useNavigation()
const { currentProjectInfo } = useProject()

// 用 useCookie 保证 SSR/CSR 初始渲染一致，避免 hydration mismatch
const _collapsedCookie = useCookie('moyu_sidebar_collapsed', { default: () => '0' })
const collapsed = computed({
  get: () => _collapsedCookie.value === '1',
  set: (v: boolean) => { _collapsedCookie.value = v ? '1' : '0' },
})

function syncCollapsed() {
  if (import.meta.client) {
    window.dispatchEvent(new CustomEvent('moyu-sidebar-toggle', { detail: collapsed.value }))
  }
}

function toggleCollapse() {
  collapsed.value = !collapsed.value
  if (import.meta.client) {
    localStorage.setItem('moyu_sidebar_collapsed', collapsed.value ? '1' : '0')
    syncCollapsed()
  }
}

// 同步旧 localStorage 数据到 cookie（首次访问时）
if (import.meta.client) {
  onMounted(() => {
    const saved = localStorage.getItem('moyu_sidebar_collapsed')
    if (saved !== null && _collapsedCookie.value !== saved) {
      _collapsedCookie.value = saved
      collapsed.value = saved === '1'
      nextTick(() => syncCollapsed())
    }
  })
}

// 管理员入口（全局菜单底部追加，仅管理员可见且非管理页时）
const adminGroup = computed(() => {
  if (showAdminEntry.value && !currentPath.value.startsWith('/admin')) {
    return { title: '管理', items: adminNav }
  }
  return null
})

// 判断某个 item 是否为「返回书架」（第一个置顶项，视觉突出）
function isBackToShelf(item: any, groupIndex: number) {
  return groupIndex === 0 && item.to.startsWith('/books')
}

// 管理员入口点击：用 router.push 确保客户端导航，不走 NuxtLink
const router = useRouter()
function navigateToAdmin(path: string) {
  router.push(path)
}

// 判断分组是否为管理分组（用于整个侧栏 admin 条目统一走 button+router 而非 NuxtLink）
function isAdminGroup(group: any) {
  return group.title === '管理' || (group.items && group.items.length > 0 && group.items[0]?.to?.startsWith('/admin'))
}
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
      <template v-for="(group, gi) in groupedNav" :key="group.title + '-' + gi">
        <!-- 分组标题（空标题不渲染，如返回书架/仪表盘的独立区） -->
        <div v-if="group.title" class="sidebar-group-title">{{ collapsed ? '' : group.title }}</div>
        <!-- 组间分隔线（置顶区与板块之间） -->
        <div v-else-if="gi > 0 && !collapsed" class="sidebar-group-divider"></div>
        <template v-if="isAdminGroup(group)">
          <button
            v-for="item in group.items"
            :key="item.to"
            class="sidebar-nav-item"
            :class="{ active: currentPath === item.to }"
            @click="navigateToAdmin(item.to)"
          >
            <span class="sidebar-nav-icon"><AppIcon :name="item.icon" /></span>
            <span v-if="!collapsed" class="sidebar-nav-label">{{ item.label }}</span>
          </button>
        </template>
        <SidebarNavItem
          v-else
          v-for="item in group.items"
          :key="item.to"
          :to="item.to"
          :icon="item.icon"
          :active="currentPath === item.to.split('?')[0]"
          :collapsed="collapsed"
          :class="{ 'nav-back-shelf': isBackToShelf(item, gi) }"
        >{{ collapsed ? '' : item.label }}</SidebarNavItem>
      </template>

      <!-- 管理员入口（仅客户端渲染，避免 SSR hydration mismatch） -->
      <ClientOnly>
        <template v-if="adminGroup">
          <div class="sidebar-group-title">{{ collapsed ? '' : adminGroup.title }}</div>
          <button
            v-for="item in adminGroup.items"
            :key="item.to"
            class="sidebar-nav-item"
            :class="{ active: currentPath === item.to }"
            @click="navigateToAdmin(item.to)"
          >
            <span class="sidebar-nav-icon"><AppIcon :name="item.icon" /></span>
            <span v-if="!collapsed" class="sidebar-nav-label">{{ item.label }}</span>
          </button>
        </template>
      </ClientOnly>
    </nav>

    <ClientOnly>
      <SidebarUser />
    </ClientOnly>
  </aside>
</template>
