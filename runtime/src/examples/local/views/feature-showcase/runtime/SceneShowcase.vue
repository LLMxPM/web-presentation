<!-- 文件功能：通过正式公开入口展示多序列 Scene；静态模板无需动画、Canvas 或采样即可完整呈现。 -->
<script setup lang="ts">
import { ref } from 'vue'
import AssetModel, { type ModelSceneComponent } from '@runtime-kit/public/components/assets/AssetModel.v1.vue'
import AssetAudio from '@runtime-kit/public/components/assets/AssetAudio.v1.vue'
import { useAudioCue } from '@runtime-kit/public/composables/audio/useAudioCue.v1'
import { defineModelNarration } from './scene-showcase/define-model-narration'
import { usePageScene } from '@runtime-kit/public/composables/motion/usePageScene.v1'
import { useStaticPresentation } from '@runtime-kit/public/composables/static/useStaticPresentation.v1'
import { defineShowcase, SCENE_SENTENCE } from './scene-showcase/define-scene'

const props = withDefaults(defineProps<{ modelName?: string; narrationName?: string }>(), { modelName: '', narrationName: '' })
const root = ref<HTMLElement | null>(null)
const model = ref<ModelSceneComponent | null>(null), narration = ref<HTMLMediaElement | null>(null)
const { playCue } = useAudioCue()
/** 资源组件只交出当前媒体实例，源变更与卸载后不能沿用旧目标。 */
function mediaReady(element: HTMLMediaElement): void { narration.value = element }
useStaticPresentation({ root, mode: 'default' })
usePageScene({ root, define(scene) {
  defineShowcase(scene)
  if (props.modelName || props.narrationName) {
    if (!props.modelName || !props.narrationName) throw new Error('联合样例必须同时提供真实模型与旁白资源名。')
    defineModelNarration(scene, model.value?.getHandle() ?? null, narration.value, playCue)
  }
} })
</script>

<template>
  <section id="scene-showcase" ref="root" class="scene-showcase">
    <header>
      <p class="scene-eyebrow">SCENE / 多序列协作</p>
      <h1>让内容按节奏发生</h1>
      <p>数值、文字与描边并行起步，有限任务完成后继续保留轻量装饰。</p>
    </header>
    <div class="scene-grid" :class="{ 'scene-grid--media': modelName || narrationName }">
      <article class="scene-card">
        <h2>01 / 数值变化</h2>
        <div class="scene-metric"><span data-counter>100</span><small>%</small></div>
        <p>一组数字，从零走向完整。</p>
      </article>
      <article class="scene-card">
        <h2>02 / 文字逐步呈现</h2>
        <p data-typewriter class="scene-words">{{ SCENE_SENTENCE }}</p>
        <p>跟随数值实际完成，再开始下一句。</p>
      </article>
      <article class="scene-card">
        <h2>03 / SVG 描边</h2>
        <svg viewBox="0 0 360 150" role="img" aria-label="从低到高的增长曲线">
          <path d="M20 125 H340 M20 125 V20" class="scene-axis" />
          <path data-stroke pathLength="1" d="M25 110 C85 110 75 65 135 80 S220 90 250 48 S310 40 335 20" class="scene-curve" style="stroke-dasharray:1;stroke-dashoffset:0" />
        </svg>
        <p>原生 SVG 属性，无需描边插件。</p>
      </article>
      <article class="scene-card">
        <h2>04 / 微粒流动</h2>
        <div class="scene-particles">
          <svg data-particle-poster viewBox="0 0 360 150" aria-hidden="true">
            <circle v-for="index in 18" :key="index" :cx="180 + Math.cos(index * 2.4) * 120" :cy="75 + Math.sin(index * 2.4) * 48" :r="2 + index % 3" fill="#818cf8" />
          </svg>
          <canvas width="360" height="150" aria-label="有限粒子扩散" />
          <div class="scene-sparks" aria-hidden="true"><i v-for="index in 8" :key="index" class="scene-spark" /></div>
        </div>
        <p>Canvas 有限扩散，DOM / CSS 装饰持续呼吸。</p>
      </article>
      <article v-if="modelName" class="scene-card">
        <h2>05 / 两段真实动作</h2>
        <AssetModel ref="model" :name="modelName" class="min-h-0 flex-1 w-full" />
        <p>先完成第一段，再开始第二段。</p>
      </article>
      <article v-if="narrationName" class="scene-card">
        <h2>06 / 旁白与提示</h2>
        <p>旁白实际结束后才完成本页；动作完成可播放已绑定的提示音。</p>
        <AssetAudio :name="narrationName" purpose="narration" @media-ready="mediaReady" @media-unmounted="narration = null" />
      </article>
    </div>
  </section>
</template>

<style scoped>
.scene-showcase { width:100%; height:100%; padding:3.5% 5%; box-sizing:border-box; background:var(--color-background,#f8fafc); color:var(--color-text-primary,#172554); display:flex; flex-direction:column; gap:26px; }
.scene-eyebrow { color:var(--color-primary,#4f46e5); font-size:14px; letter-spacing:3px; margin:0 0 10px; }
h1 { font-size:42px; line-height:1.2; margin:0 0 12px; font-weight:700; }
header > p:last-child, article > p:last-child { color:var(--color-text-secondary,#64748b); font-size:17px; margin:0; }
.scene-grid { display:grid; grid-template-columns:1fr 1fr; grid-template-rows:1fr 1fr; gap:20px; flex:1; min-height:0; }
.scene-card { padding:22px 28px; border:1px solid var(--color-border,#dbe3f0); background:var(--color-background-subtle,#fff); border-radius:18px; display:flex; flex-direction:column; justify-content:space-between; overflow:hidden; }
.scene-grid--media { grid-template-columns:repeat(3,1fr); }
h2 { font-size:16px; margin:0; font-weight:500; color:var(--color-primary,#4f46e5); }
.scene-metric { font-size:74px; line-height:1; font-weight:700; font-variant-numeric:tabular-nums; }
.scene-metric small { font-size:24px; margin-left:8px; }
.scene-words { font-size:28px; line-height:1.5; min-height:84px; margin:10px 0; }
.scene-card > svg, .scene-particles { width:100%; height:150px; min-height:0; }
.scene-axis { fill:none; stroke:#cbd5e1; stroke-width:1; }
.scene-curve { fill:none; stroke:#6366f1; stroke-width:4; stroke-linecap:round; }
.scene-particles { position:relative; }
.scene-particles svg, canvas { position:absolute; width:100%; height:100%; }
.scene-sparks { position:absolute; inset:16% 12%; display:flex; align-items:center; justify-content:space-between; }
.scene-spark { width:7px; height:7px; border-radius:50%; background:#38bdf8; opacity:0.7; }
</style>
