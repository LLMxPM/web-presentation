/**
 * 文件功能：执行 C3 受控长稳验收，在有头 Chromium 中连续放映多页 Scene，按固定间隔采集 JS 堆、
 * DOM/事件监听器、RAF 间隔与掉帧、媒体与 WebGL 计数、Renderer 槽位和进程数。
 *
 * 通过条件：全程无外部输入（noExternalInput）、无错误覆盖层、结束时可回到 idle 槽位。
 * 默认 30 分钟；C3_SOAK_MINUTES 可调整时长，少于 30 分钟需 C3_SOAK_ALLOW_SHORT=1（仅脚本自检）。
 * 需要跑其它验收项时用 C3_SKIP_SOAK=1 跳过本用例。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { expect, test } from '../../fixtures/test-data'
import {
  countRendererProcesses,
  forceGc,
  installC3Probes,
  openCdp,
  readC3Facts,
  readCdpCounters,
  readRendererHealth,
  resetC3Probes,
  toMib,
  writeEvidence,
} from '../../helpers/c3-probes'
import { buildRedModelGlb } from '../../helpers/media-fixtures'
import {
  archiveSandboxPage,
  configureSlideshow,
  createSandboxPage,
  enterPlayback,
  publishRoutes,
  runtimeFrame,
  uploadSandboxAsset,
} from '../../helpers/scene-sandbox'

/** 采样间隔：15 秒足以覆盖一次翻页与若干次动画循环，又不会让证据体量失控。 */
const SAMPLE_INTERVAL_MS = 15_000
/** Renderer 进程数采样间隔：进程枚举较慢，降频到每分钟一次。 */
const PROCESS_SAMPLE_INTERVAL_MS = 60_000

/** 构造长稳首页：有限动画 + 无限装饰 + 静音视频 + Canvas 2D 循环，覆盖 DOM/CSS/Canvas 与媒体元素。 */
function buildSoakMediaPage(videoName: string): string {
  return `<template>
  <main ref="root" class="soak-media-page">
    <h1 class="soak-title">长稳媒体页</h1>
    <p class="soak-counter" data-counter>0</p>
    <canvas ref="canvas" class="soak-canvas" width="320" height="180"></canvas>
    <i v-for="index in 8" :key="index" class="soak-spark" aria-hidden="true"></i>
    <AssetVideo name="${videoName}" muted class="soak-video" />
  </main>
</template>
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import AssetVideo from '@runtime-kit/public/components/assets/AssetVideo.v1.vue'
import { usePageScene } from '@runtime-kit/public/composables/motion/usePageScene.v1'
import { useStaticPresentation } from '@runtime-kit/public/composables/static/useStaticPresentation.v1'
const root = ref<HTMLElement | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)
let rafId = 0
let drawing = true
useStaticPresentation({ root, mode: 'default' })
onMounted(() => {
  const context = canvas.value?.getContext('2d')
  if (!context) return
  const tick = () => {
    if (!drawing) return
    context.clearRect(0, 0, 320, 180)
    context.fillStyle = '#0ea5e9'
    context.fillRect((Date.now() / 10) % 300, 40, 20, 20)
    rafId = window.requestAnimationFrame(tick)
  }
  rafId = window.requestAnimationFrame(tick)
})
onBeforeUnmount(() => { drawing = false; if (rafId) window.cancelAnimationFrame(rafId) })
usePageScene({ root, define(scene) {
  const output = scene.root.querySelector<HTMLElement>('[data-counter]')!
  const counter = { value: 0 }
  scene.onCleanup(() => { output.textContent = '0' })
  scene.visual({ id: 'finite', role: 'blocking', define(timeline) {
    timeline.to(counter, { value: 100, duration: 1, ease: 'none',
      onUpdate() { output.textContent = String(Math.round(counter.value)) } })
  } })
  scene.visual({ id: 'decor', role: 'ambient', repeat: -1, yoyo: true, define(timeline) {
    timeline.to('.soak-spark', { opacity: 0.25, duration: 0.8, stagger: 0.06 })
  } })
} })
</script>
<style scoped>
.soak-media-page { width: 100%; height: 100%; display: grid; place-content: center; justify-items: center; gap: 10px; background: #f8fafc; }
.soak-title { font-size: 48px; color: #b91c1c; }
.soak-counter { font-size: 24px; color: #0f172a; font-variant-numeric: tabular-nums; }
.soak-canvas { width: 320px; height: 180px; background: #e2e8f0; border-radius: 8px; }
.soak-spark { width: 8px; height: 8px; border-radius: 50%; background: #38bdf8; }
.soak-video { width: 320px; height: 180px; object-fit: cover; border-radius: 8px; }
</style>`
}

/** 构造长稳模型页：三维实例 + 无限变换装饰，覆盖 WebGL 上下文创建与释放。 */
function buildSoakModelPage(modelName: string): string {
  return `<template>
  <main ref="root" class="soak-model-page">
    <h1 class="soak-title">长稳模型页</h1>
    <AssetModel name="${modelName}" class="soak-model" />
  </main>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import AssetModel from '@runtime-kit/public/components/assets/AssetModel.v1.vue'
import { usePageScene } from '@runtime-kit/public/composables/motion/usePageScene.v1'
import { useStaticPresentation } from '@runtime-kit/public/composables/static/useStaticPresentation.v1'
const root = ref<HTMLElement | null>(null)
useStaticPresentation({ root, mode: 'default' })
usePageScene({ root, define(scene) {
  scene.visual({ id: 'float', role: 'ambient', repeat: -1, yoyo: true, define(timeline) {
    timeline.to('.soak-model', { y: -12, duration: 1.2, ease: 'sine.inOut' })
  } })
} })
</script>
<style scoped>
.soak-model-page { width: 100%; height: 100%; display: grid; place-content: center; justify-items: center; gap: 12px; background: #f1f5f9; }
.soak-title { font-size: 40px; color: #0f172a; }
.soak-model { width: 420px; height: 320px; }
</style>`
}

/** 构造过渡页，用于验证切页释放与重新挂载。 */
function buildSoakTextPage(): string {
  return `<template>
  <main ref="root" class="soak-text-page"><h1>长稳过渡页</h1></main>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { useStaticPresentation } from '@runtime-kit/public/composables/static/useStaticPresentation.v1'
const root = ref<HTMLElement | null>(null)
useStaticPresentation({ root, mode: 'default' })
</script>
<style scoped>
.soak-text-page { width: 100%; height: 100%; display: grid; place-content: center; background: #ffffff; }
h1 { font-size: 44px; color: #334155; }
</style>`
}

test('受控长稳：多页放映期间堆、监听器与帧间隔保持稳定且无外部输入', async ({ page, context, visualEditSandbox }, testInfo) => {
  const minutes = Number.parseInt(process.env.C3_SOAK_MINUTES || '30', 10)
  test.skip(process.env.C3_SKIP_SOAK === '1', '显式跳过长稳（C3_SKIP_SOAK=1）')
  const allowShort = process.env.C3_SOAK_ALLOW_SHORT === '1'
  if (minutes < 30 && !allowShort) {
    throw new Error('C3 长稳至少需要 30 分钟；仅脚本自检可设置 C3_SOAK_ALLOW_SHORT=1 缩短。')
  }
  // 有头运行是 C3 的强制条件：无头模式下 wake lock 与合成器行为不同，不能作为实机证据。
  test.skip(testInfo.project.use.headless === true, '长稳必须使用有头浏览器运行（--headed）')

  test.setTimeout((minutes + 10) * 60_000)
  const api = context.request
  const suffix = `soak-${Date.now()}`
  const videoName = `${suffix}-video`
  const modelName = `${suffix}-model`
  const createdPages: number[] = []

  await installC3Probes(page)
  await uploadSandboxAsset(api, visualEditSandbox.workspaceId, {
    name: videoName,
    type: 'video',
    mimeType: 'video/webm',
    fileName: `${videoName}.webm`,
    buffer: readFileSync(resolve('runtime/public/video/runtime-video-showcase.webm')),
  })
  await uploadSandboxAsset(api, visualEditSandbox.workspaceId, {
    name: modelName,
    type: 'model3d',
    mimeType: 'model/gltf-binary',
    fileName: `${modelName}.glb`,
    buffer: buildRedModelGlb({}),
  })

  try {
    const mediaPage = await createSandboxPage(api, visualEditSandbox, `${suffix} 媒体页`, buildSoakMediaPage(videoName))
    const modelPage = await createSandboxPage(api, visualEditSandbox, `${suffix} 模型页`, buildSoakModelPage(modelName))
    const textPage = await createSandboxPage(api, visualEditSandbox, `${suffix} 过渡页`, buildSoakTextPage())
    createdPages.push(mediaPage, modelPage, textPage)
    await configureSlideshow(api, visualEditSandbox.projectId, { mode: 'timer', delayMs: 15_000, loop: true })
    const previewUrl = await publishRoutes(api, visualEditSandbox.projectId, [
      { route: 'soak-media', pageId: mediaPage },
      { route: 'soak-model', pageId: modelPage },
      { route: 'soak-text', pageId: textPage },
    ])

    const { controls } = await enterPlayback(page, previewUrl)
    const frame = await runtimeFrame(page)
    // 静音视频在无手势下允许自动播放；强制 loop 让媒体元素在整个长稳期间持续解码。
    await frame.evaluate(() => {
      document.querySelectorAll('video').forEach(video => {
        const element = video as HTMLVideoElement
        element.muted = true
        element.loop = true
        void element.play().catch(() => undefined)
      })
    })
    await resetC3Probes(frame)
    const cdp = await openCdp(page)

    const samples: Record<string, unknown>[] = []
    const processCounts: (number | null)[] = []
    const wakeLocks = new Set<string>()
    const slots = new Set<string>()
    const startedAt = Date.now()
    let lastProcessSample = 0
    const deadline = startedAt + minutes * 60_000

    while (Date.now() < deadline) {
      const facts = await readC3Facts(frame)
      const counters = await readCdpCounters(cdp)
      const health = await readRendererHealth()
      if (health) slots.add(health.slot_state)
      wakeLocks.add((await controls.getAttribute('data-wake-lock')) ?? 'unknown')
      // 记录当前页码：不同页面的堆与监听器基线不同，必须随样本一起解释。
      const pageLabel = ((await controls.locator('.runtime-playback-controls__page').textContent()) ?? '').trim()
      let processCount: number | null = null
      if (Date.now() - lastProcessSample >= PROCESS_SAMPLE_INTERVAL_MS) {
        processCount = await countRendererProcesses()
        processCounts.push(processCount)
        lastProcessSample = Date.now()
      }
      samples.push({
        elapsedMs: Date.now() - startedAt,
        page: pageLabel,
        heapMib: toMib(counters.jsHeapUsedBytes),
        documents: counters.documents,
        nodes: counters.nodes,
        listeners: counters.jsEventListeners,
        browserRendererProcesses: counters.rendererProcesses,
        rendererServiceProcesses: processCount,
        slot: health?.slot_state ?? 'unreachable',
        raf: facts.raf,
        media: facts.media,
        gl: facts.gl,
        input: facts.input,
        errorOverlay: facts.errorOverlay,
      })
      await page.waitForTimeout(SAMPLE_INTERVAL_MS)
    }

    // 长稳结束后强制 GC 再取一次，区分真实保留与待回收对象。
    await forceGc(cdp)
    const tailFacts = await readC3Facts(frame)
    const tailCounters = await readCdpCounters(cdp)
    const heapValues = samples.map(sample => sample.heapMib as number | null).filter((value): value is number => value !== null)
    const listenerValues = samples
      .map(sample => sample.listeners as number | null)
      .filter((value): value is number => value !== null)
    const rafP95Values = samples.map(sample => (sample.raf as { p95: number }).p95)
    const evidence = {
      kind: 'c3-soak',
      generatedAt: new Date().toISOString(),
      candidateCommit: process.env.C3_CANDIDATE_COMMIT ?? 'working-tree',
      minutes,
      sampleIntervalMs: SAMPLE_INTERVAL_MS,
      samples,
      summary: {
        sampleCount: samples.length,
        heapFirstMib: heapValues[0] ?? null,
        heapLastMib: heapValues.at(-1) ?? null,
        heapGrowthMib:
          heapValues.length > 1 ? Math.round(((heapValues.at(-1) as number) - (heapValues[0] as number)) * 10) / 10 : null,
        heapTailAfterGcMib: toMib(tailCounters.jsHeapUsedBytes),
        listenerMin: listenerValues.length ? Math.min(...listenerValues) : null,
        listenerMax: listenerValues.length ? Math.max(...listenerValues) : null,
        rafP95Avg: rafP95Values.length
          ? Math.round((rafP95Values.reduce((sum, value) => sum + value, 0) / rafP95Values.length) * 10) / 10
          : null,
        rafP95Max: rafP95Values.length ? Math.max(...rafP95Values) : null,
        droppedFramesTotal: samples.reduce((sum, sample) => sum + (sample.raf as { dropped: number }).dropped, 0),
        glCreatedMax: Math.max(...samples.map(sample => (sample.gl as { created: number }).created), 0),
        glLostTotal: samples.reduce((sum, sample) => sum + (sample.gl as { lost: number }).lost, 0),
        glAliveEnd: tailFacts.gl.alive,
        mediaVideoMax: Math.max(...samples.map(sample => (sample.media as { videos: number }).videos), 0),
        rendererServiceProcessMax: processCounts.length ? Math.max(...processCounts.filter((value): value is number => value !== null)) : null,
        slots: [...slots],
        wakeLocks: [...wakeLocks],
        externalInputTotal: tailFacts.input.total,
        noExternalInput: tailFacts.input.total === 0,
        errorOverlaySeen: samples.some(sample => sample.errorOverlay === true) || tailFacts.errorOverlay,
      },
    }
    const evidencePath = await writeEvidence(testInfo, `soak-${minutes}m-${suffix}`, evidence)

    expect(evidence.summary.noExternalInput, '长稳期间出现外部输入，作为输入 guard 失败').toBe(true)
    expect(evidence.summary.errorOverlaySeen, '长稳期间出现运行时错误覆盖层').toBe(false)
    // B3 的渲染器池允许最多 4 个空闲上下文保留；长稳只约束有界，不要求归零。
    expect(evidence.summary.glAliveEnd, '长稳结束时保留的 WebGL 上下文超过有界池上限').toBeLessThanOrEqual(4)
    expect(evidence.summary.slots.filter(slot => slot === 'idle').length, 'Renderer 槽位未回到 idle').toBeGreaterThan(0)
    testInfo.annotations.push({ type: 'evidence', description: evidencePath })
    // 控制台输出便于人工复核，日志由 C3 证据目录统一收集。
    console.log(`[c3-soak] ${JSON.stringify(evidence.summary)}`)
  } finally {
    for (const pageId of createdPages) await archiveSandboxPage(api, pageId)
  }
})
