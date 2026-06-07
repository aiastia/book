<script setup lang="ts">
// 单个导航项：高亮判断在父级完成，这里只负责渲染（支持折叠态）
defineProps<{
  to: string
  icon: string
  active?: boolean
  collapsed?: boolean
}>()
</script>

<template>
  <NuxtLink :to="to" class="sidebar-nav-item" :class="{ active }">
    <span class="sidebar-nav-icon"><AppIcon :name="icon" /></span>
    <span class="sidebar-nav-label"><slot /></span>
  </NuxtLink>
</template>
