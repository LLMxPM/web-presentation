<!-- 文件功能：提供明亮、夜间与跟随系统三种界面主题偏好的顶部菜单入口。 -->
<template>
  <UiDropdownMenu :items="menuItems" side="bottom" align="end" @select="selectTheme">
    <template #trigger>
      <UiIconButton :label="triggerLabel">
        <Monitor v-if="preference === 'system'" class="h-4 w-4" />
        <Moon v-else-if="preference === 'dark'" class="h-4 w-4" />
        <Sun v-else class="h-4 w-4" />
      </UiIconButton>
    </template>
  </UiDropdownMenu>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Monitor, Moon, Sun } from '@lucide/vue'

import { UiDropdownMenu, UiIconButton } from '@/components/ui'
import type { DropdownMenuEntry } from '@/components/ui'
import { useTheme } from '@/composables/useTheme'

const { preference, setMode } = useTheme()

const triggerLabel = computed(() => {
  const label = preference.value === 'system'
    ? '跟随系统'
    : preference.value === 'dark' ? '夜间模式' : '明亮模式'
  return `界面主题：${label}`
})

const menuItems = computed<DropdownMenuEntry[]>(() => [
  { label: '跟随系统', value: 'system', icon: Monitor, active: preference.value === 'system' },
  { label: '明亮模式', value: 'light', icon: Sun, active: preference.value === 'light' },
  { label: '夜间模式', value: 'dark', icon: Moon, active: preference.value === 'dark' },
])

/** 根据菜单选择更新并持久化用户主题偏好。 */
function selectTheme(value: string): void {
  if (value === 'system' || value === 'light' || value === 'dark') {
    setMode(value)
  }
}
</script>
