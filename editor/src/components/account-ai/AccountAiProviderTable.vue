<!-- 文件功能：以管理后台表格展示账号可见的供应商配置，并抛出查看、编辑和删除操作。 -->
<template>
  <div class="min-h-0 overflow-auto">
    <table class="w-full min-w-[820px] table-fixed text-left text-sm">
      <thead class="sticky top-0 z-10 bg-canvas text-xs font-semibold text-text-muted">
        <tr>
          <th class="w-[22%] px-4 py-3">配置名称</th>
          <th class="w-[18%] px-4 py-3">供应商</th>
          <th class="w-28 px-4 py-3">类型</th>
          <th class="w-24 px-4 py-3">范围</th>
          <th class="w-36 px-4 py-3">连接状态</th>
          <th class="px-4 py-3">更新时间</th>
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
            <code class="mt-0.5 block truncate text-[11px] text-text-disabled">{{ config.provider_key }}</code>
          </td>
          <td class="truncate px-4 py-3 text-text-secondary">{{ config.provider_label }}</td>
          <td class="px-4 py-3 text-text-secondary">{{ providerTypeLabel(config) }}</td>
          <td class="px-4 py-3">
            <span class="rounded-full bg-surface-muted px-2 py-1 text-xs font-semibold text-text-secondary">
              {{ config.scope === 'global' ? '全局' : '个人' }}
            </span>
          </td>
          <td class="px-4 py-3">
            <span :class="config.has_api_key ? 'text-success-strong' : 'text-warning-strong'" class="font-semibold">
              {{ config.has_api_key ? '密钥已配置' : '缺少密钥' }}
            </span>
          </td>
          <td class="truncate px-4 py-3 text-xs text-text-muted">{{ formatDate(config.updated_at) }}</td>
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
import type { LlmProviderConfigItem } from '@/types/api'

defineProps<{ items: LlmProviderConfigItem[] }>()

const emit = defineEmits<{
  view: [config: LlmProviderConfigItem]
  edit: [config: LlmProviderConfigItem]
  delete: [config: LlmProviderConfigItem]
}>()

/** 返回供应商配置的业务类型文案。 */
function providerTypeLabel(config: LlmProviderConfigItem): string {
  return config.provider_type === 'image_generation' ? '图片生成' : 'Chat'
}

/** 将后端时间格式化为管理表格的紧凑日期。 */
function formatDate(value: string | null): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}
</script>

