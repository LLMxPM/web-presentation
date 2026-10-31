<!--
  文件用途：本地示例页，展示 AssetImage 的资源渲染、填充策略，以及资源 URL 解析工具的行为。
-->
<template>
  <ShowcasePage
    title="图片与资源解析"
    subtitle="资源通过逻辑名解析为 artifact 可访问 URL，组件只负责渲染"
    :capabilities="capabilities"
  >
    <div class="grid h-full min-h-0 grid-cols-[1.05fr_0.95fr] gap-5">
      <section class="flex min-h-0 flex-col rounded-lg border border-border-subtle bg-background-subtle p-5">
        <div class="mb-3 flex items-center gap-2">
          <Icon name="扫描" class="size-5 text-primary" />
          <h2 class="font-heading text-lg font-semibold text-primary">AssetImage</h2>
          <span class="ml-auto font-body text-xs text-secondary">fit 控制填充方式，class 控制图片框</span>
        </div>

        <div class="grid min-h-0 flex-1 grid-rows-2 gap-3">
          <div class="flex min-h-0 flex-col">
            <div class="mb-1.5 flex items-center justify-between">
              <span class="font-body text-xs text-secondary">fit="contain" · 完整展示</span>
              <span class="font-code text-xs text-secondary">flex-1</span>
            </div>
            <AssetImage
              name=""
              :fallback="sampleImageUrl"
              alt="资源示例图，完整展示"
              fit="contain"
              class="min-h-0 flex-1 w-full rounded-md border border-border bg-default p-2"
            />
          </div>

          <div class="flex min-h-0 flex-col">
            <div class="mb-1.5 flex items-center justify-between">
              <span class="font-body text-xs text-secondary">fit="cover" · 铺满裁剪</span>
              <span class="font-code text-xs text-secondary">flex-1</span>
            </div>
            <AssetImage
              name=""
              :fallback="sampleImageUrl"
              alt="资源示例图，铺满裁剪"
              fit="cover"
              class="min-h-0 flex-1 w-full overflow-hidden rounded-md border border-border bg-default"
            />
          </div>
        </div>

        <p class="mt-3 font-body text-xs leading-6 text-secondary">
          本地 fixture 没有工作空间资源清单，示例用 fallback 传入本地 URL；平台页面应传资源名
          <code class="font-code text-primary">name</code>，由 Runtime 解析成当前 artifact 的地址。
        </p>
      </section>

      <section class="flex min-h-0 flex-col gap-4">
        <div class="rounded-lg border border-border bg-background-subtle p-5">
          <div class="flex items-center gap-2">
            <h3 class="font-heading text-base font-semibold text-primary">useAssetBackground</h3>
            <span class="ml-auto font-code text-xs text-secondary">backgroundImage</span>
          </div>
          <div class="mt-3 flex h-[132px] items-end rounded-md border border-border bg-default p-4" :style="backgroundStyle">
            <span class="rounded bg-default px-2 py-1 font-code text-xs text-primary">自定义背景容器</span>
          </div>
        </div>

        <div class="flex min-h-0 flex-1 flex-col rounded-lg border border-border bg-background-subtle p-5">
          <h3 class="font-heading text-base font-semibold text-primary">resolveResourcePath 的三种结果</h3>
          <dl class="mt-3 space-y-2">
            <div v-for="row in resolveRows" :key="row.label" class="rounded-md bg-default px-3 py-2">
              <dt class="font-body text-xs text-secondary">{{ row.label }}</dt>
              <dd class="mt-0.5 truncate font-code text-xs text-primary">{{ row.value }}</dd>
            </div>
          </dl>
          <pre class="mt-auto overflow-auto rounded-md bg-default p-3 font-code text-xs leading-6 text-primary">const src = useAssetSrc('product-hero', fallbackUrl)
const bg = useAssetBackground('page-bg', fallbackUrl)</pre>
        </div>
      </section>
    </div>
  </ShowcasePage>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ShowcasePage, { type ShowcaseCapability } from '@/examples/local/components/ShowcasePage.vue'
import AssetImage from '@runtime-kit/public/components/assets/AssetImage.v1.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'
import { useAssetSrc } from '@runtime-kit/public/composables/assets/useAssetSrc.v1'
import { useAssetBackground } from '@runtime-kit/public/composables/assets/useAssetBackground.v1'
import { resolveResourcePath } from '@runtime-kit/public/utils/assets.v1'

const capabilities: ShowcaseCapability[] = [
  { name: 'AssetImage.v1', path: '@runtime-kit/public/components/assets/AssetImage.v1.vue' },
  { name: 'useAssetSrc.v1', path: '@runtime-kit/public/composables/assets/useAssetSrc.v1' },
  { name: 'useAssetBackground.v1', path: '@runtime-kit/public/composables/assets/useAssetBackground.v1' },
  { name: 'resolveResourcePath.v1', path: '@runtime-kit/public/utils/assets.v1' },
]

/** 本地示例图地址；真实页面不需要 fallback。 */
const sampleImageUrl = `${import.meta.env.BASE_URL}img/showcase/asset-sample.svg`

/** 背景解析演示：未命中资源名时回退到 fallback URL。 */
const backgroundStyle = useAssetBackground(() => '', () => sampleImageUrl)

/** 单元素解析演示：name 未命中时返回 fallback。 */
const resolvedSrc = useAssetSrc(() => '', () => sampleImageUrl)

/**
 * 三类解析输入的结果对照。
 * 说明：本地 fixture 没有 manifest.assets，未命中时按相对路径回退。
 */
const resolveRows = computed(() => [
  { label: '远程地址原样返回', value: resolveResourcePath('https://cdn.example.com/hero.png') },
  { label: '本地模式未命中 manifest', value: resolveResourcePath('product-hero') },
  { label: 'name 为空时使用 fallback', value: resolvedSrc.value },
])
</script>
