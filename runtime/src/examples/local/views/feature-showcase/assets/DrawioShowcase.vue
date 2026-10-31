<!--
  文件用途：本地示例页，展示 AssetDrawio 加载 Draw.io XML 资源并渲染图表区域。
-->
<template>
  <ShowcasePage
    title="Draw.io 图表"
    subtitle="Draw.io XML 资源按图表边界渲染，缩放与裁剪由渲染器负责"
    :capabilities="capabilities"
  >
    <div class="grid h-full min-h-0 grid-cols-[1.65fr_0.85fr] gap-5">
      <section class="flex min-h-0 flex-col rounded-lg border border-border-subtle bg-background-subtle p-4">
        <div class="mb-3 flex items-center gap-2">
          <Icon name="扫描" class="size-4 text-primary" />
          <h2 class="font-heading text-base font-semibold text-primary">sample.drawio</h2>
          <span class="ml-auto font-code text-xs text-secondary">public/img/drawio/sample.drawio</span>
        </div>
        <AssetDrawio
          name=""
          :fallback="sampleDrawioUrl"
          width="100%"
          height="100%"
          class="min-h-0 flex-1 rounded-md bg-default p-3"
        />
      </section>

      <section class="flex min-h-0 flex-col gap-4">
        <div class="rounded-lg border border-border bg-background-subtle p-5">
          <h3 class="font-heading text-base font-semibold text-primary">渲染规则</h3>
          <ul class="mt-3 space-y-2">
            <li v-for="note in notes" :key="note" class="flex gap-2 font-body text-xs leading-6 text-secondary">
              <span class="mt-2 size-1.5 shrink-0 rounded-full bg-accent3" />
              <span>{{ note }}</span>
            </li>
          </ul>
        </div>

        <div class="flex min-h-0 flex-1 flex-col rounded-lg border border-border bg-background-subtle p-5">
          <h3 class="font-heading text-base font-semibold text-primary">两种来源</h3>
          <pre class="mt-3 overflow-auto rounded-md bg-default p-3 font-code text-xs leading-6 text-primary">&lt;!-- 资源名 --&gt;
&lt;AssetDrawio name="architecture" /&gt;

&lt;!-- 直接 XML --&gt;
&lt;AssetDrawio :content="xml" /&gt;</pre>
          <p class="mt-3 font-body text-xs leading-6 text-secondary">
            导出时按 SVG 紧边界视口定位，因此不要在外层再叠加缩放 transform。
          </p>
        </div>
      </section>
    </div>
  </ShowcasePage>
</template>

<script setup lang="ts">
import ShowcasePage, { type ShowcaseCapability } from '@/examples/local/components/ShowcasePage.vue'
import AssetDrawio from '@runtime-kit/public/components/assets/AssetDrawio.v1.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'

const capabilities: ShowcaseCapability[] = [
  { name: 'AssetDrawio.v1', path: '@runtime-kit/public/components/assets/AssetDrawio.v1.vue' },
]

/** 本地示例 XML 的绝对地址；渲染器会再次解析相对路径，因此这里显式给出完整 URL。 */
const sampleDrawioUrl = new URL(`${import.meta.env.BASE_URL}img/drawio/sample.drawio`, window.location.origin).href

const notes = [
  'name 引用 render_type=drawio 的资源；content 用于直接传入 XML 文本。',
  '渲染器按图表实际边界输出 SVG 视口，空白区域会被裁掉。',
  'Backend 已生成普通 SVG/PNG 的场景应使用 AssetImage，不需要 Draw.io 渲染。',
]
</script>
