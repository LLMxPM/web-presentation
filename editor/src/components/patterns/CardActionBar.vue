<!-- 文件功能：为列表卡片提供统一的悬浮操作栏，处理显示/隐藏动画和按钮布局。 -->
<template>
  <div
    class="pointer-events-none absolute inset-x-2 bottom-2 z-20 flex translate-y-1 justify-end gap-1 opacity-0 transition-all group-hover:pointer-events-auto group-hover:translate-y-0 group-hover:opacity-100"
    :class="computedClass"
  >
    <slot />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  /** 操作栏位置，bottom 为底部，side 为侧边 */
  position?: 'bottom' | 'side'
  /** 对齐方式 */
  align?: 'start' | 'center' | 'end'
}>(), {
  position: 'bottom',
  align: 'end',
})

const computedClass = computed(() => {
  const classes: string[] = []
  
  if (props.position === 'side') {
    classes.push('inset-y-2 inset-x-auto right-2 flex-col')
  }
  
  if (props.align === 'start') {
    classes.push('justify-start')
  } else if (props.align === 'center') {
    classes.push('justify-center')
  }
  
  return classes.join(' ')
})
</script>
