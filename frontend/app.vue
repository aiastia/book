<!-- 根组件：根据路由 meta 选择 layout，默认 default -->
<!-- a-config-provider 注入 antd 主题（青蓝主色 #4D8088，对标 MuMuAINovel） -->
<script setup lang="ts">
const themeConfig = {
  token: {
    colorPrimary: '#4D8088',
    colorInfo: '#4D8088',
    colorSuccess: '#52A569',
    colorWarning: '#D49A4E',
    colorError: '#C75B5B',
    colorBgLayout: '#F8F6F1',
    colorTextBase: '#2B2B2B',
    borderRadius: 8,
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', Roboto, sans-serif",
  },
  components: {
    Button: { controlHeight: 36, borderRadius: 8 },
    Card: { borderRadiusLG: 12 },
    Layout: { headerBg: '#4D8088', siderBg: '#FFFFFF', bodyBg: '#F8F6F1' },
    Menu: { itemSelectedBg: '#EAF0F1', itemSelectedColor: '#4D8088' },
    Tooltip: { colorBgSpotlight: '#884d5c' },
  },
}
</script>

<template>
  <a-config-provider :theme="themeConfig">
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
  </a-config-provider>
</template>
