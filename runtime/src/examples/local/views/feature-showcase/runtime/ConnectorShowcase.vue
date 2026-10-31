<!--
  文件用途：本地示例页，展示 Connector 在真实 DOM 位置上绘制直线、折线、曲线、虚线与多锚点连线。
-->
<template>
  <ShowcasePage
    title="DOM 连线"
    subtitle="按元素真实位置绘制 SVG 连线，随布局变化自动重算"
    :capabilities="capabilities"
  >
    <div class="grid h-full min-h-0 grid-cols-3 grid-rows-2 gap-4">
      <article class="relative flex min-h-0 flex-col rounded-lg border border-border-subtle bg-background-subtle p-4">
        <header class="flex items-center justify-between">
          <h2 class="font-heading text-sm font-semibold text-primary">直线 · 单端点箭头</h2>
          <span class="font-code text-xs text-secondary">straight</span>
        </header>
        <div class="relative mt-3 flex flex-1 items-center justify-between gap-4 px-4">
          <div id="conn-straight-a" class="conn-box bg-primary">起点</div>
          <div id="conn-straight-b" class="conn-box bg-accent2">终点</div>
          <Connector
            from="#conn-straight-a"
            to="#conn-straight-b"
            type="straight"
            :stroke-width="3"
            color="var(--theme-accent-1)"
            arrow="end"
            from-anchor="right"
            to-anchor="left"
          />
        </div>
      </article>

      <article class="relative flex min-h-0 flex-col rounded-lg border border-border-subtle bg-background-subtle p-4">
        <header class="flex items-center justify-between">
          <h2 class="font-heading text-sm font-semibold text-primary">折线 · 双端箭头</h2>
          <span class="font-code text-xs text-secondary">polyline</span>
        </header>
        <div class="relative mt-3 flex flex-1 items-start justify-between gap-4 px-4">
          <div id="conn-poly-a" class="conn-box mt-6 bg-accent5">起点</div>
          <div id="conn-poly-b" class="conn-box mb-6 self-end bg-accent3">终点</div>
          <Connector
            from="#conn-poly-a"
            to="#conn-poly-b"
            type="polyline"
            :stroke-width="2"
            color="var(--theme-accent-2)"
            arrow="both"
            from-anchor="right"
            to-anchor="left"
          />
        </div>
      </article>

      <article class="relative flex min-h-0 flex-col rounded-lg border border-border-subtle bg-background-subtle p-4">
        <header class="flex items-center justify-between">
          <h2 class="font-heading text-sm font-semibold text-primary">曲线 · 上锚点</h2>
          <span class="font-code text-xs text-secondary">curve</span>
        </header>
        <div class="relative mt-3 flex flex-1 items-end justify-between gap-4 px-4 pb-4">
          <div id="conn-curve-a" class="conn-box bg-background-invert text-invert">起点</div>
          <div id="conn-curve-b" class="conn-box bg-accent4">终点</div>
          <Connector
            from="#conn-curve-a"
            to="#conn-curve-b"
            type="curve"
            :stroke-width="3"
            color="var(--theme-accent-3)"
            arrow="end"
            from-anchor="top"
            to-anchor="top"
            :curvature="-0.35"
          />
        </div>
      </article>

      <article class="relative flex min-h-0 flex-col rounded-lg border border-border-subtle bg-background-subtle p-4">
        <header class="flex items-center justify-between">
          <h2 class="font-heading text-sm font-semibold text-primary">虚线</h2>
          <span class="font-code text-xs text-secondary">dashed</span>
        </header>
        <div class="relative mt-3 flex flex-1 items-center justify-between gap-4 px-4">
          <div id="conn-dash-a" class="conn-box bg-accent6">起点</div>
          <div id="conn-dash-b" class="conn-box bg-primary">终点</div>
          <Connector
            from="#conn-dash-a"
            to="#conn-dash-b"
            type="straight"
            :stroke-width="2"
            color="var(--theme-text-secondary)"
            arrow="end"
            from-anchor="right"
            to-anchor="left"
            :dashed="true"
          />
        </div>
      </article>

      <article class="relative flex min-h-0 flex-col rounded-lg border border-border-subtle bg-background-subtle p-4">
        <header class="flex items-center justify-between">
          <h2 class="font-heading text-sm font-semibold text-primary">四个锚点</h2>
          <span class="font-code text-xs text-secondary">anchor</span>
        </header>
        <div class="relative mt-3 grid flex-1 grid-cols-[64px_96px_64px] grid-rows-3 items-center justify-center gap-2">
          <div id="conn-anchor-top" class="conn-anchor col-start-2 row-start-1">上</div>
          <div id="conn-anchor-left" class="conn-anchor col-start-1 row-start-2">左</div>
          <div id="conn-anchor-center" class="conn-box col-start-2 row-start-2 bg-accent2">中心</div>
          <div id="conn-anchor-right" class="conn-anchor col-start-3 row-start-2">右</div>
          <div id="conn-anchor-bottom" class="conn-anchor col-start-2 row-start-3">下</div>
          <Connector from="#conn-anchor-center" to="#conn-anchor-top" color="var(--theme-accent-2)" from-anchor="top" to-anchor="bottom" />
          <Connector from="#conn-anchor-center" to="#conn-anchor-right" color="var(--theme-accent-2)" from-anchor="right" to-anchor="left" />
          <Connector from="#conn-anchor-center" to="#conn-anchor-bottom" color="var(--theme-accent-2)" from-anchor="bottom" to-anchor="top" />
          <Connector from="#conn-anchor-center" to="#conn-anchor-left" color="var(--theme-accent-2)" from-anchor="left" to-anchor="right" arrow="both" />
        </div>
      </article>

      <article class="relative flex min-h-0 flex-col rounded-lg border border-border-subtle bg-background-subtle p-4">
        <header class="flex items-center justify-between">
          <h2 class="font-heading text-sm font-semibold text-primary">线宽与曲率</h2>
          <span class="font-code text-xs text-secondary">stroke / curvature</span>
        </header>
        <div class="relative mt-3 flex flex-1 items-center justify-between gap-4 px-4">
          <div id="conn-width-a" class="conn-box bg-accent4">起点</div>
          <div id="conn-width-b" class="conn-box bg-accent2">终点</div>
          <Connector from="#conn-width-a" to="#conn-width-b" :stroke-width="1" color="var(--theme-accent-4)" arrow="end" from-anchor="right" to-anchor="left" />
          <Connector from="#conn-width-a" to="#conn-width-b" type="curve" :stroke-width="5" color="var(--theme-accent-1)" arrow="end" from-anchor="bottom" to-anchor="bottom" :curvature="0.45" />
        </div>
      </article>
    </div>
  </ShowcasePage>
</template>

<script setup lang="ts">
import ShowcasePage, { type ShowcaseCapability } from '@/examples/local/components/ShowcasePage.vue'
import Connector from '@runtime-kit/public/components/primitives/Connector.v1.vue'

const capabilities: ShowcaseCapability[] = [
  { name: 'Connector.v1', path: '@runtime-kit/public/components/primitives/Connector.v1.vue' },
]
</script>

<style scoped>
/* 演示方块统一尺寸，避免各示例各自内联样式。 */
.conn-box {
  display: flex;
  width: 96px;
  height: 60px;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  color: #fff;
  font-family: var(--tw-font-body);
  font-size: 14px;
  font-weight: 700;
}

.conn-anchor {
  display: flex;
  width: 48px;
  height: 48px;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: var(--tw-color-accent2);
  color: #fff;
  font-family: var(--tw-font-body);
  font-size: 12px;
  font-weight: 600;
  justify-self: center;
}
</style>
