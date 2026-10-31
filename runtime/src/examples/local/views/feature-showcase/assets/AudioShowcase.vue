<!--
  文件用途：本地示例页，展示音频资源播放与语义音效接口；本地 fixture 直连内部播放器。
-->
<template>
  <ShowcasePage
    title="音频与音效"
    subtitle="内容音频按资源名播放，交互音效只按语义 key 请求"
    :capabilities="capabilities"
  >
    <div class="grid h-full min-h-0 grid-cols-[1.05fr_0.95fr] gap-5">
      <section class="flex min-h-0 flex-col rounded-lg border border-border-subtle bg-background-subtle p-5">
        <div class="mb-3 flex items-center gap-2">
          <Icon name="slider" class="size-5 text-primary" />
          <h2 class="font-heading text-lg font-semibold text-primary">内容音频</h2>
          <span class="ml-auto font-code text-xs text-secondary">{{ audioUrl.split('/').pop() }}</span>
        </div>

        <div class="rounded-md border border-border bg-default p-4">
          <AudioViewer
            :src="audioUrl"
            purpose="content"
            :controls="true"
            :volume="volume"
            :playback-rate="playbackRate"
            :loop="loop"
            preload="metadata"
            class="w-full"
          />
        </div>

        <div class="mt-4 grid grid-cols-2 gap-4">
          <label class="space-y-2">
            <span class="font-body text-xs text-secondary">音量 volume · {{ volume.toFixed(2) }}</span>
            <input v-model.number="volume" type="range" min="0" max="1" step="0.05" class="w-full accent-primary" />
          </label>
          <label class="space-y-2">
            <span class="font-body text-xs text-secondary">速率 playbackRate</span>
            <select v-model.number="playbackRate" class="showcase-input">
              <option :value="0.75">0.75×</option>
              <option :value="1">1×</option>
              <option :value="1.5">1.5×</option>
              <option :value="2">2×</option>
            </select>
          </label>
        </div>

        <label class="mt-3 flex items-center gap-2.5">
          <input v-model="loop" type="checkbox" class="size-4 accent-primary" />
          <span class="font-body text-xs text-primary">循环播放</span>
        </label>

        <div class="mt-4 rounded-md bg-default p-4">
          <div class="flex h-20 items-end gap-1">
            <span
              v-for="(bar, index) in waveform"
              :key="index"
              class="flex-1 rounded-sm bg-accent2"
              :style="{ height: `${bar}%` }"
            />
          </div>
          <div class="mt-2 flex items-center justify-between font-body text-xs text-secondary">
            <span>示例音频 · 1.6s 衰减和弦</span>
            <span class="font-code">22050 Hz · mono</span>
          </div>
        </div>

        <p class="mt-4 font-body text-xs leading-6 text-secondary">
          本地 fixture 直连内部播放器验证音频链路；平台页面统一使用 AssetAudio，用
          <code class="font-code text-primary">name</code> 引用资源，用
          <code class="font-code text-primary">purpose=&quot;narration&quot;</code> 标记旁白，并用
          <code class="font-code text-primary">createSceneMediaTask</code> 显式登记播放任务。
        </p>

        <div class="mt-4 grid grid-cols-2 gap-3">
          <div class="rounded-md bg-default p-3">
            <p class="font-code text-xs font-semibold text-primary">purpose="content"</p>
            <p class="mt-1 font-body text-xs leading-6 text-secondary">由用户主动播放，可循环、可显示原生控件。</p>
          </div>
          <div class="rounded-md bg-default p-3">
            <p class="font-code text-xs font-semibold text-primary">purpose="narration"</p>
            <p class="mt-1 font-body text-xs leading-6 text-secondary">禁止循环；登记为 blocking 任务后，scene_end 等待实际播放结束再翻页。</p>
          </div>
        </div>
      </section>

      <section class="flex min-h-0 flex-col gap-4">
        <div class="rounded-lg border border-border bg-background-subtle p-5">
          <div class="flex items-center gap-2">
            <Icon name="添加联系人" class="size-4 text-primary" />
            <h3 class="font-heading text-base font-semibold text-primary">useAudioCue 交互音效</h3>
          </div>
          <p class="mt-2 font-body text-xs leading-6 text-secondary">
            页面只声明语义 key，音量、绑定资源和播放许可由 Runtime 统一管理；无 provider 时稳定返回
            unavailable，不暴露 URL 或音量绕过入口。
          </p>
          <div class="mt-3 flex items-center gap-3">
            <button type="button" class="rounded-md bg-primary px-4 py-2 font-body text-sm font-semibold text-invert" @click="triggerCue">
              播放 interaction.tap
            </button>
            <span class="font-code text-xs text-secondary">结果 · {{ cueResult }}</span>
          </div>
        </div>

        <div class="flex min-h-0 flex-1 flex-col rounded-lg border border-border bg-background-subtle p-5">
          <h3 class="font-heading text-base font-semibold text-primary">AssetAudio 契约</h3>
          <dl class="mt-3 space-y-1.5">
            <div v-for="row in contractRows" :key="row.name" class="flex gap-3 rounded-md bg-default px-3 py-2">
              <dt class="w-24 shrink-0 font-code text-xs text-primary">{{ row.name }}</dt>
              <dd class="min-w-0 flex-1 font-body text-xs leading-6 text-secondary">{{ row.note }}</dd>
            </div>
          </dl>
          <pre class="mt-4 min-h-0 flex-1 overflow-auto rounded-md bg-default p-3 font-code text-xs leading-6 text-primary">{{ narrationExample }}</pre>
        </div>
      </section>
    </div>
  </ShowcasePage>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import ShowcasePage, { type ShowcaseCapability } from '@/examples/local/components/ShowcasePage.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'
import AudioViewer from '@runtime-kit/internal/renderers/AudioViewer.vue'
import { useAudioCue } from '@runtime-kit/public/composables/audio/useAudioCue.v1'

const capabilities: ShowcaseCapability[] = [
  { name: 'AssetAudio.v1', path: '@runtime-kit/public/components/assets/AssetAudio.v1.vue' },
  { name: 'useAudioCue.v1', path: '@runtime-kit/public/composables/audio/useAudioCue.v1' },
  { name: 'AudioViewer', path: 'internal/renderers/AudioViewer.vue', local: true },
]

const audioUrl = `${import.meta.env.BASE_URL}audio/runtime-audio-showcase.wav`

const volume = ref(0.8)
const playbackRate = ref(1)
const loop = ref(false)
const cueResult = ref('未触发')

const { playCue } = useAudioCue()

/** 平台页面旁白的最小接线；资源组件提供目标，Scene 任务负责播放与完成聚合。 */
const narrationExample = [
  "import { ref, shallowRef } from 'vue'",
  "import AssetAudio from '@runtime-kit/public/components/assets/AssetAudio.v1.vue'",
  "import { usePageScene } from '@runtime-kit/public/composables/motion/usePageScene.v1'",
  "import { useStaticPresentation } from '@runtime-kit/public/composables/static/useStaticPresentation.v1'",
  "import { createSceneMediaTask } from '@runtime-kit/public/composables/media/createSceneMediaTask.v1'",
  '',
  'const root = ref<HTMLElement | null>(null)',
  'const voice = shallowRef<HTMLAudioElement | null>(null)',
  "useStaticPresentation({ root, mode: 'default' })",
  'usePageScene({ root, define(scene) {',
  '  scene.task(createSceneMediaTask({',
  "    id: 'voice', role: 'blocking', target: () => voice.value,",
  '  }))',
  '} })',
  '',
  '// 模板放在 <section ref="root"> 内；项目翻页模式设为 scene_end。',
  '<AssetAudio name="narration-intro" purpose="narration"',
  '  @media-ready="voice = $event" @media-unmounted="voice = null" />',
].join('\n')

/** 静态波形示意：按衰减和弦的形状生成，只用于可视化，不参与播放。 */
const waveform = Array.from({ length: 48 }, (_, index) => (
  Math.round(18 + 78 * Math.exp(-index / 11) * (0.55 + 0.45 * Math.abs(Math.sin(index * 1.7))))
))

/** 触发一次语义音效并回显结果，验证无 provider 时的稳定降级。 */
async function triggerCue(): Promise<void> {
  cueResult.value = String(await playCue('interaction.tap'))
}

const contractRows = [
  { name: 'name', note: '资源逻辑名；未命中时按 fallback 处理，不猜测路径。' },
  { name: 'purpose', note: 'content 由用户播放；narration 禁止循环，必须显式登记 Scene 媒体任务。' },
  { name: 'controls', note: '默认内容音频显示控件，旁白隐藏控件。' },
  { name: 'volume', note: '组件级音量 0–1，旁白还要叠加项目 master × narration。' },
  { name: 'playbackRate', note: '0.5–2 倍速；超出范围按安全默认值处理。' },
  { name: 'preload', note: '静态呈现上下文强制降为 none，避免截图时触发下载。' },
]
</script>

<style scoped>
.showcase-input {
  width: 100%;
  border-radius: 8px;
  border: 1px solid var(--tw-color-border-default);
  background: var(--tw-color-bg-default);
  padding: 8px 10px;
  color: var(--tw-color-text-primary);
  font-size: 13px;
  outline: none;
}
</style>
