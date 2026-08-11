<!-- 文件功能：以管理后台表格展示账号可见的模型配置，并抛出查看、编辑和删除操作。 -->
<template>
  <div class="min-h-0 overflow-auto">
    <table class="w-full min-w-[940px] table-fixed text-left text-sm">
      <thead class="sticky top-0 z-10 bg-canvas text-xs font-semibold text-text-muted">
        <tr>
          <th class="w-[18%] px-4 py-3">模型名称</th>
          <th class="w-[22%] px-4 py-3">模型 ID</th>
          <th class="w-[18%] px-4 py-3">供应商配置</th>
          <th class="w-28 px-4 py-3">类型</th>
          <th class="w-24 px-4 py-3">范围</th>
          <th class="px-4 py-3">能力</th>
          <th class="w-44 px-4 py-3 text-right">操作</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-border-muted">
        <tr
          v-for="config in items"
          :key="config.id"
          class="cursor-pointer bg-surface transition hover:bg-surface-hover"
          @click="emit('view', config)"
        >
          <td class="px-4 py-3">
            <p class="truncate font-semibold text-text-strong">{{ config.name }}</p>
            <span :class="config.status === 'active' ? 'text-success-strong' : 'text-text-disabled'" class="mt-0.5 block text-xs font-semibold">
              {{ config.status === 'active' ? '启用' : '不可用' }}
            </span>
          </td>
          <td class="px-4 py-3"><code class="block truncate text-xs text-text-secondary">{{ config.model_id }}</code></td>
          <td class="truncate px-4 py-3 text-text-secondary">{{ config.provider_config_name }}</td>
          <td class="px-4 py-3 text-text-secondary">{{ config.model_type === 'image_generation' ? '图片生成' : 'Chat' }}</td>
          <td class="px-4 py-3">
            <span class="rounded-full bg-surface-muted px-2 py-1 text-xs font-semibold text-text-secondary">
              {{ config.scope === 'global' ? '全局' : '个人' }}
            </span>
          </td>
          <td class="px-4 py-3 text-xs text-text-muted">{{ capabilityLabel(config) }}</td>
          <td class="px-4 py-3 text-right" @click.stop>
            <div class="flex justify-end gap-1">
              <UiButton variant="ghost" size="sm" @click="emit('view', config)">查看</UiButton>
              <UiButton v-if="config.editable" variant="ghost" size="sm" @click="emit('edit', config)">编辑</UiButton>
              <UiButton v-if="config.editable" variant="danger" size="sm" @click="emit('delete', config)">删除</UiButton>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { UiButton } from '@/components/ui'
import type { LlmConfigItem } from '@/types/api'

defineProps<{ items: LlmConfigItem[] }>()

const emit = defineEmits<{
  view: [config: LlmConfigItem]
  edit: [config: LlmConfigItem]
  delete: [config: LlmConfigItem]
}>()

/** 汇总模型在列表中需要快速识别的能力。 */
function capabilityLabel(config: LlmConfigItem): string {
  if (config.model_type === 'image_generation') return '图片生成'
  const reasoningMode = config.reasoning_mode ?? (config.thinking_enabled ? 'enabled' : 'auto')
  const reasoning = reasoningMode === 'enabled'
    ? `推理 ${config.reasoning_level ?? config.thinking_effort ?? 'medium'}`
    : reasoningMode === 'disabled' ? '推理关闭' : '推理跟随模型'
  return [reasoning, config.supports_image_input ? '图片输入' : ''].filter(Boolean).join(' · ')
}
</script>
