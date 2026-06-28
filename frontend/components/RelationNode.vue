<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'

const props = defineProps<{
  data: { label: string; role: string; isMain: boolean }
}>()

const role = props.data?.role || '配角'
const colors: Record<string, string> = {
  '主角': '#FF6B35', '反派': '#C41E3A', '配角': '#4D8CBF', '路人': '#8C8C8C',
}
const color = colors[role] || colors['配角']
const size = role === '主角' ? 80 : role === '反派' ? 72 : role === '配角' ? 64 : 56
</script>

<template>
  <div
    class="relation-node"
    :style="{
      background: color,
      width: size + 'px', height: size + 'px',
      fontSize: role === '主角' ? '14px' : '12px',
      fontWeight: role === '主角' ? '800' : '600',
    }"
  >
    <Handle type="source" :position="Position.Top" id="s-top" />
    <Handle type="source" :position="Position.Bottom" id="s-bottom" />
    <Handle type="target" :position="Position.Top" id="t-top" />
    <Handle type="target" :position="Position.Bottom" id="t-bottom" />
    <span class="node-label">{{ data.label }}</span>
  </div>
</template>

<style scoped>
.relation-node {
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  border: 3px solid rgba(0,0,0,0.12);
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  position: relative;
}
.node-label {
  text-align: center;
  line-height: 1.2;
  padding: 4px;
  word-break: break-all;
}
</style>
