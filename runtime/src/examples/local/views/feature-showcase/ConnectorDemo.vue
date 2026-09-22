<template>
  <DefaultContentPage title="连接线组件演示" subtitle="Connector Component Demo">
    <template #content>
      <div class="p-8 relative grid grid-cols-2 gap-8">
        <section class="mb-4 relative ">
          <h3 class="text-2xl font-bold mb-4 text-[var(--color-text-primary)]">直线连接 (Straight)</h3>
          <div class="flex justify-between items-center gap-16 px-24 py-2 relative min-h-[150px]">
            <div
id="box1"
              class="w-[120px] h-20 flex items-center justify-center text-white font-bold rounded-lg shadow-md bg-blue-500">
              起点</div>
            <div
id="box2"
              class="w-[120px] h-20 flex items-center justify-center text-white font-bold rounded-lg shadow-md bg-green-500">
              终点</div>
          </div>
          <Connector
from="#box1" to="#box2" type="straight" :stroke-width="3" color="var(--theme-accent-1)" arrow="end"
            from-anchor="right" to-anchor="left" />
        </section>

        <!-- 示例 2: 折线连接 -->
        <section class="mb-4 relative ">
          <h3 class="text-2xl font-bold mb-4 text-[var(--color-text-primary)]">折线连接 (Polyline)</h3>
          <div class="flex justify-between items-center gap-16 px-24 py-2 relative min-h-[150px]">
            <div
id="box3"
              class="w-[120px] h-20 flex items-center justify-center text-white font-bold rounded-lg shadow-md bg-purple-500">
              起点</div>
            <div
id="box4"
              class="w-[120px] h-20 flex items-center justify-center mt-32 text-white font-bold rounded-lg shadow-md bg-orange-500">
              终点</div>
          </div>
          <Connector
from="#box3" to="#box4" type="polyline" :stroke-width="2" color="var(--theme-accent-2)"
            arrow="both" from-anchor="right" to-anchor="left" />
        </section>

        <!-- 示例 3: 曲线连接 -->
        <section class="mb-4 relative ">
          <h3 class="text-2xl font-bold mb-4 text-[var(--color-text-primary)]">曲线连接 (Curve)</h3>
          <div class="flex justify-between items-center gap-16 px-24 py-2 relative min-h-[150px] mt-10">
            <div
id="box5"
              class="w-[120px] h-20 flex items-center justify-center text-invert font-bold rounded-lg shadow-md bg-background-invert">
              起点</div>
            <div
id="box6"
              class="w-[120px] h-20 flex items-center justify-center text-invert font-bold rounded-lg shadow-md bg-accent2">
              终点</div>
          </div>
          <Connector
from="#box5" to="#box6" type="curve" :stroke-width="3" color="var(--theme-accent-3)" arrow="end"
            from-anchor="top" to-anchor="top" :curvature="-0.3" />
        </section>

        <!-- 示例 4: 虚线连接 -->
        <section class="mb-4 relative ">
          <h3 class="text-2xl font-bold mb-4 text-[var(--color-text-primary)]">虚线连接 (Dashed)</h3>
          <div class="flex justify-between items-center gap-16 px-24 py-2 relative min-h-[150px]">
            <div
id="box7"
              class="w-[120px] h-20 flex items-center justify-center text-white font-bold rounded-lg shadow-md bg-yellow-500">
              起点</div>
            <div
id="box8"
              class="w-[120px] h-20 flex items-center justify-center text-white font-bold rounded-lg shadow-md bg-red-500">
              终点</div>
          </div>
          <Connector
from="#box7" to="#box8" type="straight" :stroke-width="2" color="var(--theme-text-primary)"
            arrow="end" from-anchor="right" to-anchor="left" :dashed="true" />
        </section>

        <!-- 示例 5: 锚点位置 -->
        <section class="mb-4 relative ">
          <h3 class="text-2xl font-bold mb-4 text-[var(--color-text-primary)]">锚点位置 (Anchor Points)</h3>
          <div
            class="grid grid-cols-[100px_200px_100px] grid-rows-[100px_100px_100px] gap-8 p-16 justify-center items-center relative min-h-[150px]">
            <div
id="box9"
              class="w-[120px] h-20 flex items-center justify-center text-white font-bold rounded-lg shadow-md bg-indigo-500 col-start-2 row-start-2 justify-self-center self-center">
              中心元素</div>
            <div
id="box10"
              class="w-[60px] h-[60px] flex items-center justify-center text-white font-bold rounded-lg shadow-md text-sm bg-teal-500 col-start-2 row-start-1 justify-self-center self-center">
              上</div>
            <div
id="box11"
              class="w-[60px] h-[60px] flex items-center justify-center text-white font-bold rounded-lg shadow-md text-sm bg-teal-500 col-start-3 row-start-2 justify-self-center self-center">
              右</div>
            <div
id="box12"
              class="w-[60px] h-[60px] flex items-center justify-center text-white font-bold rounded-lg shadow-md text-sm bg-teal-500 col-start-2 row-start-3 justify-self-center self-center">
              下</div>
            <div
id="box13"
              class="w-[60px] h-[60px] flex items-center justify-center text-white font-bold rounded-lg shadow-md text-sm bg-teal-500 col-start-1 row-start-2 justify-self-center self-center">
              左</div>
          </div>
          <Connector
from="#box9" to="#box10" type="straight" :stroke-width="2" color="#14b8a6" from-anchor="top"
            to-anchor="bottom" />
          <Connector
from="#box9" to="#box11" type="straight" :stroke-width="2" color="#14b8a6" from-anchor="right"
            to-anchor="left" />
          <Connector
from="#box9" to="#box12" type="straight" :stroke-width="2" color="#14b8a6" from-anchor="bottom"
            to-anchor="top" />
          <Connector
from="#box9" to="#box13" type="straight" :stroke-width="2" color="#14b8a6" from-anchor="left"
            to-anchor="right" arrow="both" />
        </section>

        <!-- 示例 6: 不同粗细 -->
        <section class="mb-4 relative ">
          <h3 class="text-2xl font-bold mb-4 text-[var(--color-text-primary)]">不同粗细 (Stroke Width)</h3>
          <div class="flex justify-between items-center gap-16 px-24 py-2 relative min-h-[250px] ">
            <div
id="box14"
              class="w-[120px] h-20 flex items-center justify-center text-white font-bold rounded-lg shadow-md bg-rose-500">
              起点</div>
            <div
id="box15"
              class="w-[120px] h-20 flex items-center justify-center text-white font-bold rounded-lg shadow-md bg-emerald-500">
              终点</div>
          </div>
          <Connector
from="#box14" to="#box15" type="straight" :stroke-width="1" color="#10b981" arrow="end"
            from-anchor="right" to-anchor="left" />
          <Connector
from="#box14" to="#box15" type="curve" :stroke-width="5" color="var(--theme-accent-4)" arrow="end"
            from-anchor="bottom" to-anchor="bottom" :curvature="0.5" />
        </section>

      </div>
    </template>
  </DefaultContentPage>
</template>

<script setup lang="ts">
import DefaultContentPage from '@/runtime-kit/public/components/page/templates/DefaultContentPage.vue'
import Connector from '@runtime-kit/public/components/primitives/Connector.v1.vue'
</script>
