<!-- 文件功能：以管理后台表格展示账号可见的模型配置，并抛出查看、编辑和删除操作。 -->
<template>
  <div class="min-h-0 overflow-x-auto overflow-y-auto">
    <table class="w-full min-w-[960px] table-fixed text-left text-sm">
      <thead class="sticky top-0 z-10 bg-canvas text-xs font-semibold text-text-muted">
        <tr>
          <th class="min-w-[190px] px-4 py-3 whitespace-nowrap">模型名称</th>
          <th class="min-w-[180px] px-4 py-3 whitespace-nowrap">模型 ID</th>
          <th class="min-w-[150px] px-4 py-3 whitespace-nowrap">供应商配置</th>
          <th class="w-28 px-4 py-3 whitespace-nowrap">类型</th>
          <th class="w-20 px-4 py-3 whitespace-nowrap">范围</th>
          <th class="min-w-[160px] px-4 py-3 whitespace-nowrap">能力</th>
          <th class="w-48 px-4 py-3 text-right whitespace-nowrap">操作</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-border-muted">
        <tr
          v-for="config in items"
          :key="config.id"
          class="cursor-pointer bg-surface transition hover:bg-surface-hover"
          @click="handleRowClick(config)"
        >
          <!-- 模型名称与状态 -->
          <td class="px-4 py-3 min-w-[190px]">
            <div class="flex items-center gap-1.5 min-w-0">
              <span class="truncate font-semibold text-text-strong" :title="config.name">{{ config.name }}</span>
              <UiBadge v-if="defaultModelId === config.id" tone="success" size="sm" class="shrink-0">
                当前默认
              </UiBadge>
            </div>
            <div class="mt-1 flex items-center gap-1.5 text-xs">
              <span
                class="inline-block h-1.5 w-1.5 rounded-full shrink-0"
                :class="config.status === 'active' ? 'bg-success' : 'bg-text-disabled'"
              />
              <span
                :class="config.status === 'active' ? 'text-success-strong' : 'text-text-disabled'"
                class="font-medium whitespace-nowrap"
              >
                {{ config.status === 'active' ? '启用' : '停用' }}
              </span>
            </div>
          </td>

          <!-- 模型 ID（等宽字体与快速复制） -->
          <td class="px-4 py-3 min-w-[180px]">
            <div class="group inline-flex max-w-full items-center gap-1.5">
              <code
                class="truncate rounded border border-border-muted bg-canvas px-1.5 py-0.5 font-mono text-xs text-text-secondary"
                :title="config.model_id"
              >
                {{ config.model_id }}
              </code>
              <UiIconButton
                size="xs"
                variant="ghost"
                :label="copiedModelId === config.model_id ? '已复制' : '复制模型 ID'"
                :title="copiedModelId === config.model_id ? '已复制' : '复制模型 ID'"
                class="opacity-60 hover:opacity-100 focus:opacity-100"
                @click.stop="handleCopyModelId(config.model_id)"
              >
                <Check v-if="copiedModelId === config.model_id" class="h-3 w-3 text-success-strong" />
                <Copy v-else class="h-3 w-3" />
              </UiIconButton>
            </div>
          </td>

          <!-- 供应商配置 -->
          <td class="px-4 py-3 min-w-[150px]">
            <span class="block truncate font-medium text-text" :title="config.provider_config_name">
              {{ config.provider_config_name }}
            </span>
          </td>

          <!-- 模型类型 -->
          <td class="w-28 px-4 py-3 whitespace-nowrap">
            <UiBadge :tone="config.model_type === 'image_generation' ? 'info' : 'accent'" size="sm">
              {{ config.model_type === 'image_generation' ? '图片生成' : 'Chat' }}
            </UiBadge>
          </td>

          <!-- 范围 -->
          <td class="w-20 px-4 py-3 whitespace-nowrap">
            <UiBadge tone="neutral" size="sm">
              {{ config.scope === 'global' ? '全局' : '个人' }}
            </UiBadge>
          </td>

          <!-- 能力标识组 -->
          <td class="px-4 py-3 min-w-[160px]">
            <div class="flex flex-wrap items-center gap-1">
              <template v-if="config.model_type === 'image_generation'">
                <UiBadge tone="info" size="sm">图片生成</UiBadge>
              </template>
              <template v-else>
                <UiBadge
                  v-if="config.model_capability_json?.supports_reasoning"
                  tone="accent"
                  size="sm"
                >
                  支持推理
                </UiBadge>
                <UiBadge
                  v-if="config.supports_image_input"
                  tone="success"
                  size="sm"
                >
                  图片输入
                </UiBadge>
                <span
                  v-if="!config.model_capability_json?.supports_reasoning && !config.supports_image_input"
                  class="text-xs text-text-disabled"
                >
                  —
                </span>
              </template>
            </div>
          </td>

          <!-- 表格行操作 -->
          <td class="w-48 px-4 py-3 text-right whitespace-nowrap" @click.stop>
            <div class="flex items-center justify-end gap-1 shrink-0">
              <UiButton variant="ghost" size="sm" @click="emit('view', config)">查看</UiButton>
              <UiButton v-if="config.editable" variant="ghost" size="sm" @click="emit('edit', config)">编辑</UiButton>
              <UiButton
                v-if="config.editable"
                variant="ghost"
                size="sm"
                class="text-danger hover:bg-danger-muted hover:text-danger-strong"
                @click="emit('delete', config)"
              >
                删除
              </UiButton>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Check, Copy } from '@lucide/vue'
import { UiBadge, UiButton, UiIconButton } from '@/components/ui'
import type { LlmConfigItem } from '@/types/api'

interface Props {
  items: LlmConfigItem[]
  defaultModelId?: number | null
}

defineProps<Props>()

const emit = defineEmits<{
  view: [config: LlmConfigItem]
  edit: [config: LlmConfigItem]
  delete: [config: LlmConfigItem]
}>()

const copiedModelId = ref<string | null>(null)
let copyTimer: ReturnType<typeof setTimeout> | null = null

/** 复制模型 ID 到剪贴板并展示瞬时反馈。 */
async function handleCopyModelId(modelId: string) {
  try {
    await navigator.clipboard.writeText(modelId)
    copiedModelId.value = modelId
    if (copyTimer) clearTimeout(copyTimer)
    copyTimer = setTimeout(() => {
      copiedModelId.value = null
    }, 1500)
  } catch (error) {
    console.error('复制模型 ID 失败:', error)
  }
}

/** 行点击响应：可编辑配置直接进入编辑，只读配置进入查看。 */
function handleRowClick(config: LlmConfigItem) {
  if (config.editable) {
    emit('edit', config)
  } else {
    emit('view', config)
  }
}
</script>
