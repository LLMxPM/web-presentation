<!-- 文件功能：仅在开发环境展示 Editor UI Primitive 的主要视觉与交互状态。 -->
<template>
  <main class="min-h-screen overflow-y-auto bg-canvas p-6 text-text">
    <div class="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <header class="flex flex-col gap-2 border-b border-border pb-4">
        <p class="text-xs font-medium uppercase tracking-wide text-text-muted">Editor UI Lab</p>
        <h1 class="m-0 text-title-lg">基础组件状态展示</h1>
        <p class="m-0 text-sm text-text-secondary">仅在本地开发环境提供，用于核对首批 UI Primitive 的视觉与可访问性状态。</p>
      </header>

      <section class="grid gap-4 lg:grid-cols-2" aria-labelledby="button-title">
        <article class="rounded-ui-lg border border-border bg-surface p-4">
          <h2 id="button-title" class="m-0 text-title-sm">UiButton</h2>
          <p class="mt-1 text-sm text-text-muted">变体、禁用与加载状态。</p>
          <div class="mt-4 flex flex-wrap gap-2">
            <UiButton>主要操作</UiButton>
            <UiButton variant="secondary">次要操作</UiButton>
            <UiButton variant="ghost">幽灵操作</UiButton>
            <UiButton variant="danger">危险操作</UiButton>
            <UiButton disabled>禁用操作</UiButton>
            <UiButton loading>保存中</UiButton>
          </div>
        </article>

        <article class="rounded-ui-lg border border-border bg-surface p-4">
          <h2 class="m-0 text-title-sm">UiIconButton</h2>
          <p class="mt-1 text-sm text-text-muted">带可访问名称的图标按钮。</p>
          <div class="mt-4 flex flex-wrap items-center gap-2">
            <UiIconButton label="新增" variant="primary"><Plus /></UiIconButton>
            <UiIconButton label="编辑" variant="secondary"><Pencil /></UiIconButton>
            <UiIconButton label="删除" variant="danger"><Trash2 /></UiIconButton>
            <UiIconButton label="更多操作" disabled><MoreHorizontal /></UiIconButton>
            <UiIconButton label="加载中" loading><RefreshCw /></UiIconButton>
          </div>
        </article>
      </section>

      <section class="grid gap-4 lg:grid-cols-2" aria-labelledby="input-title">
        <article class="rounded-ui-lg border border-border bg-surface p-4">
          <h2 id="input-title" class="m-0 text-title-sm">UiInput 与 UiFormField</h2>
          <div class="mt-4 grid gap-4">
            <UiFormField label="项目名称" description="用于工作台中的项目识别。" required v-slot="{ inputId, describedBy, invalid }">
              <UiInput v-model="projectName" :input-id="inputId" :described-by="describedBy" :invalid="invalid" placeholder="输入项目名称" clearable />
            </UiFormField>
            <UiFormField label="路由标识" error="路由标识不能为空" required v-slot="{ inputId, describedBy, invalid }">
              <UiInput :input-id="inputId" :described-by="describedBy" :invalid="invalid" model-value="" placeholder="例如：annual-report" />
            </UiFormField>
            <UiInput model-value="不可编辑的值" disabled aria-label="禁用输入框" />
          </div>
        </article>

        <article class="rounded-ui-lg border border-border bg-surface p-4">
          <h2 class="m-0 text-title-sm">UiBadge</h2>
          <p class="mt-1 text-sm text-text-muted">状态、类型和版本等紧凑信息。</p>
          <div class="mt-4 flex flex-wrap items-center gap-2">
            <UiBadge>草稿</UiBadge>
            <UiBadge tone="accent">v2</UiBadge>
            <UiBadge tone="success">已发布</UiBadge>
            <UiBadge tone="warning">待确认</UiBadge>
            <UiBadge tone="danger">构建失败</UiBadge>
            <UiBadge tone="info" size="md">运行中</UiBadge>
          </div>
        </article>
      </section>

      <section class="grid gap-4 lg:grid-cols-2" aria-labelledby="selection-title">
        <article class="rounded-ui-lg border border-border bg-surface p-4">
          <h2 id="selection-title" class="m-0 text-title-sm">UiRadioGroup</h2>
          <p class="mt-1 text-sm text-text-muted">单选项支持描述、禁用和方向键导航。</p>
          <UiRadioGroup v-model="publishMode" class="mt-4" aria-label="发布方式" :options="publishModeOptions" />
        </article>

        <article class="rounded-ui-lg border border-border bg-surface p-4">
          <h2 class="m-0 text-title-sm">UiSegmentedControl</h2>
          <p class="mt-1 text-sm text-text-muted">适合紧凑的类型、范围和视图切换。</p>
          <UiSegmentedControl v-model="assetScope" class="mt-4" aria-label="资源范围" :options="assetScopeOptions" />
        </article>
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { MoreHorizontal, Pencil, Plus, RefreshCw, Trash2 } from '@lucide/vue'

import { UiBadge, UiButton, UiFormField, UiIconButton, UiInput, UiRadioGroup, UiSegmentedControl } from '@/components/ui'

/** 展示输入与真实 v-model 行为，初始值留空以便观察 placeholder。 */
const projectName = ref('')

/** 展示 RadioGroup 与 SegmentedControl 的受控选择行为。 */
const publishMode = ref('draft')
const assetScope = ref('all')
const publishModeOptions = [
  { label: '保留草稿', value: 'draft', description: '仅工作空间成员可见。' },
  { label: '立即发布', value: 'published', description: '完成审核后对协作者生效。' },
  { label: '归档', value: 'archived', disabled: true, description: '需要先下线当前版本。' },
]
const assetScopeOptions = [
  { label: '全部', value: 'all' },
  { label: '图片', value: 'image' },
  { label: '文件', value: 'file' },
]
</script>
