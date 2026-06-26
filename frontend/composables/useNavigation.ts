// 侧边栏导航数据 + 当前页高亮判断
// 说明：统一管理侧边栏菜单（项目内 / 全局），已对接后端全部页面

export interface NavItem {
  label: string
  to: string
  icon: string // 对应 AppIcon.vue 里的 name
}

export interface NavGroup {
  title: string        // 分组标题；空字符串表示无标题（用于置顶独立项）
  items: NavItem[]
}

// 项目内菜单（进入某本书后显示的创作功能）
// 结构：返回书架（置顶独立）+ 仪表盘 + 设定板块 + 大纲与写作板块
// 顺序 = 写一本书的自然创作流程：先建世界 → 再设角色 → 然后大纲 → 最后写章节 → 辅以分析/伏笔

// 返回书架：置顶独立项
const backToShelfNav: NavItem = { label: '返回书架', to: '/books', icon: 'book' }
// 仪表盘：紧随返回书架
const dashboardNav: NavItem = { label: '仪表盘', to: '/dashboard', icon: 'home' }

// 设定板块：世界观/角色/关系/组织/职业/物品/地点/写作风格
const settingsNav: NavItem[] = [
  // —— 第1步：世界观设定（时间/地理/规则/势力组织） ——
  { label: '世界设定', to: '/worldview', icon: 'book' },
  // —— 第2步：角色设定 ——
  { label: '角色设定', to: '/characters', icon: 'users' },
  { label: '关系图谱', to: '/relations', icon: 'star' },
  { label: '组织势力', to: '/organizations', icon: 'globe' },
  { label: '职业体系', to: '/careers', icon: 'home' },
  { label: '物品道具', to: '/items', icon: 'star' },
  { label: '地点地图', to: '/locations', icon: 'book' },
  { label: '写作风格', to: '/writing-style', icon: 'edit' },
]

// 大纲与写作板块：大纲/章节/伏笔/剧情分析/故事记忆
const writingNav: NavItem[] = [
  // —— 第3步：故事大纲 ——
  { label: '故事大纲', to: '/outline', icon: 'outline' },
  // —— 第4步：正式写章节 ——
  { label: '故事章节', to: '/chapters', icon: 'book' },
  // —— 第5步：写作辅助 ——
  { label: '伏笔管理', to: '/foreshadows', icon: 'star' },
  { label: '剧情分析', to: '/analysis', icon: 'activity' },
  { label: '故事记忆', to: '/memories', icon: 'edit' },
]

// 全局管理菜单（书架层 / 未选书时显示）
const globalNav: NavItem[] = [
  { label: '我的书架', to: '/books', icon: 'book' },
  { label: '拆书导入', to: '/book-import', icon: 'edit' },
  { label: '灵感模式', to: '/inspire', icon: 'message' },
  { label: 'AI 设置', to: '/ai-settings', icon: 'bot' },
  { label: '提示词模板', to: '/prompts', icon: 'message' },
  { label: 'Skill 管理', to: '/skill-manage', icon: 'star' },
  { label: 'MCP 插件', to: '/mcp', icon: 'plugin' },
  { label: '帮助说明', to: '/help', icon: 'help' },
  { label: '关于我们', to: '/about', icon: 'info' },
]

// 管理员菜单（仅管理员可见）
const adminNav: NavItem[] = [
  { label: '用户管理', to: '/admin/users', icon: 'users' },
  { label: '系统设置', to: '/admin/system', icon: 'bot' },
]

// 哪些路径走"项目内菜单"
const projectPages = [
  '/dashboard', '/outline', '/chapters', '/characters',
  '/worldview', '/foreshadows', '/analysis', '/writing-style', '/relations', '/organizations', '/careers', '/memories', '/items', '/locations', '/chapter-reader',
]

export function useNavigation() {
  const route = useRoute()
  const { currentProjectId } = useProject()
  const { user } = useAuth()
  const currentPath = computed(() => route.path.replace(/\.html$/, '').replace(/\/$/, '') || '/')
  const isProject = computed(() => projectPages.some(p => currentPath.value.startsWith(p)))
  const isAdmin = computed(() => currentPath.value.startsWith('/admin'))

  // 给项目页面的链接自动追加 ?pid=（刷新时可恢复项目上下文）
  // SSR 和客户端同时追加，保证 HTML 一致性，避免水合警告
  function withPid(item: NavItem): NavItem {
    if (isProject.value && currentProjectId.value) {
      return { ...item, to: item.to + '?pid=' + currentProjectId.value }
    }
    return item
  }

  // 扁平化的项目菜单（兼容旧调用方：BatchGeneratePanel 等不直接用，但保留）
  const nav = computed<NavItem[]>(() => {
    if (isAdmin.value) return adminNav
    if (!isProject.value) return globalNav
    return [backToShelfNav, dashboardNav, ...settingsNav, ...writingNav].map(withPid)
  })

  // 分组化的项目菜单（新：AppSidebar 用）
  const groupedNav = computed<NavGroup[]>(() => {
    if (isAdmin.value) {
      // admin 页面也保持全局导航，管理入口在底部单独追加
      return [{ title: '导航', items: globalNav }, { title: '管理', items: adminNav }]
    }
    if (!isProject.value) {
      return [{ title: '导航', items: globalNav }]
    }
    // 项目内：返回书架置顶 + 仪表盘 + 设定 + 大纲与写作
    return [
      { title: '', items: [withPid(backToShelfNav)] },
      { title: '', items: [withPid(dashboardNav)] },
      { title: '设定', items: settingsNav.map(withPid) },
      { title: '大纲与写作', items: writingNav.map(withPid) },
    ]
  })

  // 管理员入口（全局菜单底部，仅管理员可见）
  const showAdminEntry = computed(() => !!user.value?.is_admin)
  return { nav, groupedNav, isProject, currentPath, adminNav, showAdminEntry }
}