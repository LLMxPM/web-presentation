<!--
  文件用途：本地示例页，说明 Runtime Kit 公开能力边界与非资源类能力分组。
-->
<template>
  <DefaultContentPage title="Runtime Kit 能力边界" subtitle="面向页面源码、工作空间组件和 Agent 的公开运行时契约">
    <template #content>
      <div class="grid h-full grid-cols-[1.1fr_0.9fr] gap-8 p-6">
        <section class="space-y-5">
          <div class="rounded-lg border border-border bg-background-subtle p-6">
            <div class="mb-4 flex items-center gap-3">
              <Icon name="home" class="size-6 text-primary" />
              <h2 class="font-heading text-2xl font-semibold text-primary">Runtime Kit 不是通用 UI 组件库</h2>
            </div>
            <p class="font-body text-base leading-8 text-secondary">
              Runtime Kit 只公开必须依赖 Runtime 上下文才能稳定完成的能力，例如页面尺寸、
              路由目录、导航控制、图标解析、DOM 连线和资源 URL 解析。普通内容块、卡片、
              栅格和页面视觉结构仍由页面源码直接生成。
            </p>
          </div>

          <div class="grid grid-cols-2 gap-5">
            <article
              v-for="group in capabilityGroups"
              :key="group.title"
              class="rounded-lg border border-border-default bg-default p-5 shadow-theme-sm"
            >
              <div class="mb-3 flex items-center gap-2">
                <Icon :name="group.icon" class="size-4 text-accent2" />
                <h3 class="font-heading text-xl font-semibold text-primary">{{ group.title }}</h3>
              </div>
              <p class="font-body text-sm leading-7 text-secondary">{{ group.description }}</p>
            </article>
          </div>
        </section>

        <aside class="rounded-lg border border-border bg-background-muted p-6">
          <h3 class="font-heading text-xl font-semibold text-primary">公开导入边界</h3>
          <div class="mt-5 space-y-4">
            <div
              v-for="item in importBoundaries"
              :key="item.path"
              class="rounded-md border border-border-default bg-default p-4"
            >
              <p class="font-mono text-sm text-primary">{{ item.path }}</p>
              <p class="mt-2 font-body text-sm leading-6 text-secondary">{{ item.note }}</p>
            </div>
          </div>
        </aside>
      </div>
    </template>
  </DefaultContentPage>
</template>

<script setup lang="ts">
import DefaultContentPage from '@/runtime-kit/public/components/page/templates/DefaultContentPage.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'

/**
 * Runtime Kit 能力分组说明。
 * 输入：无；输出：模板渲染用静态说明列表。
 */
const capabilityGroups = [
  {
    title: '页面上下文',
    icon: '缩小',
    description: '读取页面真实宽高、构造标准画布样式，并让页面内容在固定设计尺寸内稳定排版。',
  },
  {
    title: '路由上下文',
    icon: '路由-copy',
    description: '读取当前页、总页数、目录项和页码映射，供页面自行渲染目录、页码和导航控件。',
  },
  {
    title: '运行时 DOM 能力',
    icon: '扫描',
    description: '在真实浏览器 DOM 中完成连线、图标 inline、主题色解析等静态生成难以保证的行为。',
  },
  {
    title: '资源解析工具',
    icon: 'slider',
    description: '将资源逻辑名解析为当前发布产物可访问 URL，但不替页面决定布局和视觉样式。',
  },
]

/**
 * 公开与私有导入路径边界。
 */
const importBoundaries = [
  {
    path: '@runtime-kit/public/...',
    note: '页面源码和工作空间组件可使用的公开路径，必须来自 manifest 中的 exports。',
  },
  {
    path: '@runtime-kit/internal/...',
    note: '仅供 Runtime 内部包装组件使用，页面源码不应直接引用。',
  },
  {
    path: '@/core、@/runtime-shell',
    note: 'Runtime 壳层私有实现，不属于 Backend、Editor 或 Agent 的页面生成契约。',
  },
]
</script>
