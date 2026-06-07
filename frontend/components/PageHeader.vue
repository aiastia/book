<script setup lang="ts">
// 页面顶部 header：标题 + 右侧操作区(插槽)
defineProps<{
  title?: string
}>()
</script>

<template>
  <header class="page-header">
    <span class="page-header-title">{{ title }}</span>
    <div class="page-header-actions">
      <slot name="actions" />
    </div>
  </header>
</template>
