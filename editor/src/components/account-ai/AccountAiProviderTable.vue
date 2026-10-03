<!-- 文件功能：以管理后台表格展示账号可见的供应商配置，并抛出查看、编辑和删除操作。 -->
<template>
  <div class="min-h-0 overflow-x-auto overflow-y-auto">
    <table class="w-full min-w-[960px] table-fixed text-left text-sm">
      <thead class="sticky top-0 z-10 bg-canvas text-xs font-semibold text-text-muted">
        <tr>
          <th class="min-w-[200px] px-4 py-3 whitespace-nowrap">配置名称</th>
          <th class="min-w-[170px] px-4 py-3 whitespace-nowrap">供应商</th>
          <th class="w-28 px-4 py-3 whitespace-nowrap">类型</th>
          <th class="w-20 px-4 py-3 whitespace-nowrap">范围</th>
          <th class="w-36 px-4 py-3 whitespace-nowrap">连接状态</th>
          <th class="w-36 px-4 py-3 whitespace-nowrap">更新时间</th>
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
          <!-- 配置名称与 Provider Key -->
          <td class="px-4 py-3 min-w-[200px]">
            <p class="truncate font-semibold text-text-strong" :title="config.name">{{ config.name }}</p>
            <div class="mt-1 group inline-flex max-w-full items-center gap-1.5">
              <code
                class="truncate rounded border border-border-muted bg-canvas px-1.5 py-0.5 font-mono text-[11px] text-text-secondary"
                :title="config.provider_key"
              >
                {{ config.provider_key }}
              </code>
              <UiIconButton
                size="xs"
                variant="ghost"
                :label="copiedProviderKey === config.provider_key ? '已复制' : '复制 Provider Key'"
                :title="copiedProviderKey === config.provider_key ? '已复制' : '复制 Provider Key'"
                class="opacity-60 hover:opacity-100 focus:opacity-100"
                @click.stop="handleCopyProviderKey(config.provider_key)"
              >
                <Check v-if="copiedProviderKey === config.provider_key" class="h-2.5 w-2.5 text-success-strong" />
                <Copy v-else class="h-2.5 w-2.5" />
              </UiIconButton>
            </div>
          </td>

          <!-- 供应商平台与 Base URL 提示 -->
          <td class="px-4 py-3 min-w-[170px]">
            <p class="truncate font-medium text-text" :title="config.provider_label">{{ config.provider_label }}</p>
            <p
              v-if="config.base_url"
              class="mt-0.5 truncate text-[11px] text-text-muted font-mono"
              :title="`接入地址：${config.base_url}`"
            >
              {{ config.base_url }}
            </p>
          </td>

          <!-- 类型 -->
          <td class="w-28 px-4 py-3 whitespace-nowrap">
            <UiBadge :tone="config.provider_type === 'image_generation' ? 'info' : 'accent'" size="sm">
              {{ config.provider_type === 'image_generation' ? '图片生成' : 'Chat' }}
            </UiBadge>
          </td>

          <!-- 范围 -->
          <td class="w-20 px-4 py-3 whitespace-nowrap">
            <UiBadge tone="neutral" size="sm">
              {{ config.scope === 'global' ? '全局' : '个人' }}
            </UiBadge>
          </td>

          <!-- 连接状态 -->
          <td class="w-36 px-4 py-3 whitespace-nowrap">
            <div class="flex items-center gap-1.5 text-xs font-medium">
              <span
                class="inline-block h-2 w-2 rounded-full shrink-0"
                :class="config.has_api_key ? 'bg-success' : 'bg-warning'"
              />
              <span :class="config.has_api_key ? 'text-success-strong' : 'text-warning-strong'">
                {{ config.has_api_key ? '密钥已配置' : '缺少密钥' }}
              </span>
            </div>
          </td>

          <!-- 更新时间（回退使用创建时间，避免整列为空） -->
          <td class="w-36 truncate px-4 py-3 text-xs text-text-muted whitespace-nowrap">
            {{ formatDateTime(config.updated_at || config.created_at) }}
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
import type { LlmProviderConfigItem } from '@/types/api'
import { formatDateTime } from '@/utils/format'

interface Props {
  items: LlmProviderConfigItem[]
}

defineProps<Props>()

const emit = defineEmits<{
  view: [config: LlmProviderConfigItem]
  edit: [config: LlmProviderConfigItem]
  delete: [config: LlmProviderConfigItem]
}>()

const copiedProviderKey = ref<string | null>(null)
let copyTimer: ReturnType<typeof setTimeout> | null = null

/** 复制 Provider Key 到剪贴板并展示瞬时反馈。 */
async function handleCopyProviderKey(key: string) {
  try {
    await navigator.clipboard.writeText(key)
    copiedProviderKey.value = key
    if (copyTimer) clearTimeout(copyTimer)
    copyTimer = setTimeout(() => {
      copiedProviderKey.value = null
    }, 1500)
  } catch (error) {
    console.error('复制 Provider Key 失败:', error)
  }
}

/** 行点击响应：可编辑配置直接进入编辑，只读配置进入查看。 */
function handleRowClick(config: LlmProviderConfigItem) {
  if (config.editable) {
    emit('edit', config)
  } else {
    emit('view', config)
  }
}
</script>
