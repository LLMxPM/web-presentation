<!--
  文件用途：本地能力示例页统一骨架，集中展示页面标题、本页演示的公开能力与示例区域。
  约束：能力标签只声明公开导入路径；本地 fixture 直连内部渲染器时用 local 标记显式说明。
-->
<template>
  <DefaultContentPage :title="title" :subtitle="subtitle">
    <template #content>
      <div class="flex h-full min-h-0 flex-col gap-4">
        <ul v-if="capabilities.length" class="flex flex-wrap items-center gap-x-3 gap-y-2">
          <li class="font-body text-xs font-semibold tracking-wider text-secondary">本页能力</li>
          <li
            v-for="item in capabilities"
            :key="item.name"
            class="flex items-center gap-2 rounded-full border border-border-subtle bg-background-subtle py-1 pl-3 pr-2"
            :title="item.path"
          >
            <span class="font-code text-xs font-semibold text-primary">{{ item.name }}</span>
            <span class="font-code text-xs text-secondary">{{ shortPath(item.path) }}</span>
            <span
              v-if="item.local"
              class="rounded-full bg-accent3-100 px-2 py-0.5 font-body text-xs font-semibold text-accent3-800"
            >
              本地直连
            </span>
          </li>
        </ul>
        <div class="min-h-0 flex-1">
          <slot />
        </div>
      </div>
    </template>
  </DefaultContentPage>
</template>

<script setup lang="ts">
import DefaultContentPage from '@/runtime-kit/public/components/page/templates/DefaultContentPage.vue'

/** 本页演示的能力声明；path 必须是 manifest 中的公开导入路径。 */
export interface ShowcaseCapability {
  /** manifest 中的能力名，如 AssetImage.v1 */
  name: string
  /** 公开导入路径 */
  path: string
  /** 本地 fixture 无法走资源清单、直连内部渲染器时为 true */
  local?: boolean
}

interface Props {
  /** 页面标题 */
  title: string
  /** 页面副标题 */
  subtitle?: string
  /** 本页演示的能力列表 */
  capabilities: ShowcaseCapability[]
}

withDefaults(defineProps<Props>(), { subtitle: '' })

/**
 * 压缩公开导入路径，去掉公共前缀便于在标签内阅读。
 * @param path manifest 提供的完整导入路径
 * @returns 省略 @runtime-kit/public/ 前缀的路径
 */
function shortPath(path: string): string {
  return path.replace('@runtime-kit/public/', '').replace('@runtime-kit/', '')
}
</script>
