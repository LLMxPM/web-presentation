<!-- 文件功能：基于 Reka UI 为图标和紧凑控件提供提示信息。 -->
<template>
  <TooltipProvider :delay-duration="delayDuration"><TooltipRoot><TooltipTrigger as-child><slot name="trigger" /></TooltipTrigger><TooltipPortal><TooltipContent :side="side" :side-offset="sideOffset" class="z-popover rounded-md bg-overlay px-2 py-1 text-xs text-text-inverse shadow-lg"><slot>{{ content }}</slot></TooltipContent></TooltipPortal></TooltipRoot></TooltipProvider>
</template>
<script setup lang="ts">
import { TooltipContent, TooltipPortal, TooltipProvider, TooltipRoot, TooltipTrigger } from 'reka-ui'
withDefaults(defineProps<{ content?: string; side?: 'top' | 'right' | 'bottom' | 'left'; sideOffset?: number; delayDuration?: number }>(), { side: 'top', sideOffset: 6, delayDuration: 300 })
</script>
