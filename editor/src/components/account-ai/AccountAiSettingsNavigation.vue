<!-- 文件功能：提供账号 AI 设置管理后台的一级模块导航，并适配桌面窄栏与移动端顶部标签。 -->
<template>
  <aside class="ai-settings-navigation min-h-0 border-border bg-surface">
    <div class="hidden h-full min-h-0 flex-col p-2 min-[960px]:flex">
      <p class="navigation-title px-3 pb-2 pt-1 text-xs font-bold text-text-disabled">AI 设置</p>
      <nav class="space-y-1" aria-label="AI 设置模块">
        <UiButton
          v-for="item in items"
          :key="item.value"
          variant="ghost"
          content-align="start"
          class="navigation-button h-auto w-full min-w-0 py-2.5"
          :class="modelValue === item.value ? 'bg-surface-selected text-accent-hover' : 'text-text-secondary'"
          :aria-current="modelValue === item.value ? 'page' : undefined"
          @click="emit('update:modelValue', item.value)"
        >
          <component :is="item.icon" class="h-4 w-4 shrink-0" />
          <span class="navigation-label min-w-0 flex-1 truncate text-left font-semibold">{{ item.label }}</span>
          <span
            class="navigation-meta shrink-0 rounded-full bg-surface-muted px-2 py-0.5 text-[11px] font-semibold text-text-muted"
            :class="item.warning ? 'bg-warning-muted text-warning-strong' : ''"
          >
            {{ item.meta }}
          </span>
        </UiButton>
      </nav>
    </div>

    <UiTabs
      class="min-[960px]:hidden"
      :model-value="modelValue"
      :items="mobileItems"
      list-class="grid grid-cols-3 border-b-0 px-2 pt-2 [&>button]:min-w-0 [&>button]:truncate"
      content-class="hidden"
      @update:model-value="emit('update:modelValue', $event as AiSettingsSection)"
    />
  </aside>
</template>

<script setup lang="ts">
import { Bot, Image, MessagesSquare } from '@lucide/vue'
import { computed } from 'vue'

import { UiButton, UiTabs } from '@/components/ui'
import type { AiSettingsSection } from './account-ai-settings-types'

const props = defineProps<{
  modelValue: AiSettingsSection
  modelCount: number
  providerCount: number
  assistantReady: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [value: AiSettingsSection] }>()

const items = computed(() => [
  { value: 'assistant' as const, label: '内容助手', meta: props.assistantReady ? '已就绪' : '待配置', warning: !props.assistantReady, icon: Bot },
  { value: 'chat' as const, label: '聊天模型', meta: `${props.modelCount}`, warning: false, icon: MessagesSquare },
  { value: 'image' as const, label: '图片生成', meta: `${props.providerCount}`, warning: false, icon: Image },
])

const mobileItems = computed(() => items.value.map(item => ({ label: item.label, value: item.value })))
</script>

<style scoped>
.ai-settings-navigation {
  border-right-width: 1px;
}

@media (min-width: 960px) and (max-width: 1179px) {
  .navigation-title,
  .navigation-label,
  .navigation-meta {
    display: none;
  }

  .navigation-button :deep(> span) {
    justify-content: center;
  }
}

@media (max-width: 959px) {
  .ai-settings-navigation {
    border-right-width: 0;
    border-bottom-width: 1px;
  }
}
</style>

