<script setup lang="ts">
// 页面顶部 header：标题 + 可选返回链接 + 右侧操作区(插槽)
defineProps<{
  title?: string
  back?: string       // 返回链接的路径，如 '/' 或 '/books'
  backLabel?: string  // 返回链接的文字，默认 '← 返回首页'
}>()
</script>

<template>
  <header class="page-header">
    <div class="page-header-left">
      <NuxtLink v-if="back" :to="back" class="page-header-back">
        {{ backLabel || '← 返回首页' }}
      </NuxtLink>
      <span class="page-header-title">{{ title }}</span>
    </div>
    <div class="page-header-actions">
      <slot name="actions" />
    </div>
  </header>
</template>
