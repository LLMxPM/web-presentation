/**
 * 文件功能：执行 A04 渲染器保留曲线与 WebGL 上下文丢失/恢复演练。
 *
 * 通过反复进出三维页面采集 GC 后的 JS 堆、DOM/监听器、存活 WebGL 上下文与浏览器渲染进程，
 * 供 C3 给出「修复」或「接受」结论；同时用 WEBGL_lose_context 验证丢失后的恢复或明确错误。
 */
import { expect, test } from '../../fixtures/test-data'
import {
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

/** 默认进出轮次；C3 要求 100 次，脚本自检可下调但不作为验收证据。 */
const DEFAULT_CYCLES = 100
/** 需要在曲线里保留的采样轮次。 */
const CHECKPOINTS = [0, 10, 25, 50, 75, 100]

/** 三维页面：只保留一个可见模型，便于观察上下文创建与释放。 */
function buildA04ModelPage(modelName: string): string {
  return `<template>
  <main ref="root" class="a04-model-page">
    <AssetModel name="${modelName}" class="a04-model" />
  </main>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import AssetModel from '@runtime-kit/public/components/assets/AssetModel.v1.vue'
import { useStaticPresentation } from '@runtime-kit/public/composables/static/useStaticPresentation.v1'
const root = ref<HTMLElement | null>(null)
useStaticPresentation({ root, mode: 'default' })
</script>
<style scoped>
.a04-model-page { width: 100%; height: 100%; display: grid; place-items: center; background: #f8fafc; }
.a04-model { width: 480px; height: 360px; }
</style>`
}

/** 过渡页：不含任何画布，离开模型页后用于观察上下文是否释放。 */
function buildA04PlainPage(): string {
  return `<template>
  <main ref="root" class="a04-plain-page"><h1>A04 过渡页</h1></main>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { useStaticPresentation } from '@runtime-kit/public/composables/static/useStaticPresentation.v1'
const root = ref<HTMLElement | null>(null)
useStaticPresentation({ root, mode: 'default' })
</script>
<style scoped>
.a04-plain-page { width: 100%; height: 100%; display: grid; place-items: center; background: #ffffff; }
h1 { font-size: 40px; color: #334155; }
</style>`
}

test('A04：模型页进出循环的堆与 WebGL 上下文保留曲线', async ({ page, context, visualEditSandbox }, testInfo) => {
  test.setTimeout(30 * 60_000)
  const cycles = Number.parseInt(process.env.C3_A04_CYCLES || String(DEFAULT_CYCLES), 10)
  const api = context.request
  const suffix = `a04-${Date.now()}`
  const modelName = `${suffix}-model`
  const createdPages: number[] = []

  await installC3Probes(page)
  await uploadSandboxAsset(api, visualEditSandbox.workspaceId, {
    name: modelName,
    type: 'model3d',
    mimeType: 'model/gltf-binary',
    fileName: `${modelName}.glb`,
    buffer: buildRedModelGlb({}),
  })

  try {
    const modelPage = await createSandboxPage(api, visualEditSandbox, `${suffix} 模型页`, buildA04ModelPage(modelName))
    const plainPage = await createSandboxPage(api, visualEditSandbox, `${suffix} 过渡页`, buildA04PlainPage())
    createdPages.push(modelPage, plainPage)
    await configureSlideshow(api, visualEditSandbox.projectId, { mode: 'manual' })
    // 放映从第一页开始：先过渡页、后模型页，循环推进即可反复进出模型页。
    const previewUrl = await publishRoutes(api, visualEditSandbox.projectId, [
      { route: 'a04-plain', pageId: plainPage },
      { route: 'a04-model', pageId: modelPage },
    ])

    const { controls } = await enterPlayback(page, previewUrl)
    const frame = await runtimeFrame(page)
    await resetC3Probes(frame)
    const cdp = await openCdp(page)
    const next = controls.locator('button[aria-label="下一页"]')
    const previous = controls.locator('button[aria-label="上一页"]')
    /**
     * 切页期间控制条会临时禁用；先等按钮可用再点击。
     * 全幅页面内容会盖住控制条命中区域，这里用事件派发触发同一个 Vue 处理器，
     * 命中遮挡情况单独记录到证据，供 C3 判定是否需要修复。
     */
    const advance = async (button: typeof next) => {
      await expect(button).toBeEnabled({ timeout: 30_000 })
      await button.dispatchEvent('click')
    }
    const hitTest = await frame.evaluate(() => {
      const button = document.querySelector<HTMLButtonElement>('.runtime-playback-controls button[aria-label="上一页"]')
      if (!button) return { blocked: null as boolean | null, topElement: 'missing' }
      const rect = button.getBoundingClientRect()
      const top = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2)
      return {
        blocked: top !== null && !button.contains(top),
        topElement: top ? `${top.tagName.toLowerCase()}.${(top.getAttribute('class') || '').split(' ')[0]}` : 'none',
      }
    })

    const curve: Record<string, unknown>[] = []
    const checkpoints = new Set(CHECKPOINTS.map(value => Math.min(value, cycles)))
    const sample = async (cycle: number, phase: string) => {
      await forceGc(cdp)
      const facts = await readC3Facts(frame)
      const counters = await readCdpCounters(cdp)
      const health = await readRendererHealth()
      curve.push({
        cycle,
        phase,
        heapMib: toMib(facts.heapUsedBytes),
        documents: counters.documents,
        nodes: counters.nodes,
        listeners: counters.jsEventListeners,
        browserRendererProcesses: counters.rendererProcesses,
        glCreated: facts.gl.created,
        glLost: facts.gl.lost,
        glAlive: facts.gl.alive,
        liveCanvases: facts.media.canvases,
        slot: health?.slot_state ?? 'unreachable',
      })
    }

    await sample(0, 'start')
    for (let cycle = 1; cycle <= cycles; cycle += 1) {
      // 进入模型页：等待模型页容器与 canvas 出现，确保 WebGL 上下文确实建立。
      await advance(next)
      await frame.locator('.a04-model-page').waitFor({ state: 'visible', timeout: 20_000 })
      await frame.locator('canvas').first().waitFor({ state: 'visible', timeout: 20_000 })
      // 离开模型页：退回过渡页，触发实例销毁与上下文释放。
      await advance(previous)
      await frame.locator('.a04-plain-page').waitFor({ state: 'visible', timeout: 20_000 })
      if (checkpoints.has(cycle)) await sample(cycle, 'after-leave')
    }

    const heapValues = curve
      .filter(entry => entry.phase === 'after-leave' || entry.phase === 'start')
      .map(entry => entry.heapMib as number | null)
      .filter((value): value is number => value !== null)
    const last = curve.at(-1) ?? {}
    const rendererProcessValues = curve
      .map(entry => entry.browserRendererProcesses as number | null)
      .filter((value): value is number => typeof value === 'number')
    const evidence = {
      kind: 'c3-a04-retention',
      generatedAt: new Date().toISOString(),
      candidateCommit: process.env.C3_CANDIDATE_COMMIT ?? 'working-tree',
      cycles,
      shortened: cycles < DEFAULT_CYCLES,
      controlBarHitTest: hitTest,
      curve,
      summary: {
        heapStartMib: heapValues[0] ?? null,
        heapEndMib: heapValues.at(-1) ?? null,
        heapGrowthMib:
          heapValues.length > 1 ? Math.round(((heapValues.at(-1) as number) - (heapValues[0] as number)) * 10) / 10 : null,
        listenersStart: (curve[0]?.listeners as number | null) ?? null,
        listenersEnd: (last.listeners as number | null) ?? null,
        glCreatedTotal: last.glCreated ?? null,
        glLostTotal: last.glLost ?? null,
        glAliveEnd: last.glAlive ?? null,
        liveCanvasesEnd: last.liveCanvases ?? null,
        browserRendererProcessMax: rendererProcessValues.length ? Math.max(...rendererProcessValues) : null,
      },
    }
    const evidencePath = await writeEvidence(testInfo, `a04-${cycles}cycles-${suffix}`, evidence)
    testInfo.annotations.push({ type: 'evidence', description: evidencePath })
    console.log(`[c3-a04] ${JSON.stringify(evidence.summary)}`)

    // 结构调整类断言只保证演练真的完成了进出，不把保留量阈值写死；结论由 C3 依据曲线给出。
    expect(curve.length).toBeGreaterThan(1)
    expect((last.liveCanvases as number) ?? 0).toBe(0)
  } finally {
    for (const pageId of createdPages) await archiveSandboxPage(api, pageId)
  }
})

test('A04：WEBGL_lose_context 丢失后能恢复或给出明确错误', async ({ page, context, visualEditSandbox }, testInfo) => {
  test.setTimeout(5 * 60_000)
  const api = context.request
  const suffix = `webgl-${Date.now()}`
  const modelName = `${suffix}-model`
  const createdPages: number[] = []

  await installC3Probes(page)
  await uploadSandboxAsset(api, visualEditSandbox.workspaceId, {
    name: modelName,
    type: 'model3d',
    mimeType: 'model/gltf-binary',
    fileName: `${modelName}.glb`,
    buffer: buildRedModelGlb({}),
  })

  try {
    const modelPage = await createSandboxPage(api, visualEditSandbox, `${suffix} 模型页`, buildA04ModelPage(modelName))
    createdPages.push(modelPage)
    await configureSlideshow(api, visualEditSandbox.projectId, { mode: 'manual' })
    const previewUrl = await publishRoutes(api, visualEditSandbox.projectId, [{ route: 'webgl', pageId: modelPage }])
    await enterPlayback(page, previewUrl)
    const frame = await runtimeFrame(page)
    await frame.locator('canvas').first().waitFor({ state: 'visible', timeout: 20_000 })

    const outcome = await frame.evaluate(async () => {
      const registry = (window as unknown as { __c3Gl?: WebGLRenderingContext[] }).__c3Gl ?? []
      const context = registry.find(candidate => !candidate.isContextLost())
      if (!context) return { supported: false, reason: '页面未创建可用的 WebGL 上下文' }
      const extension = context.getExtension('WEBGL_lose_context')
      if (!extension) return { supported: false, reason: 'WEBGL_lose_context 扩展不可用' }
      const waitFor = (type: string, timeoutMs: number) =>
        new Promise<boolean>(resolve => {
          const timer = setTimeout(() => resolve(false), timeoutMs)
          context.canvas.addEventListener(type, () => {
            clearTimeout(timer)
            resolve(true)
          }, { once: true })
        })
      const lostPromise = waitFor('webglcontextlost', 5_000)
      extension.loseContext()
      const lost = await lostPromise
      const lostImmediately = context.isContextLost()
      // Chromium 在丢失事件同一次任务内忽略恢复请求，先让出一个宏任务再请求恢复。
      await new Promise(resolveDelay => setTimeout(resolveDelay, 300))
      const restoredPromise = waitFor('webglcontextrestored', 10_000)
      extension.restoreContext()
      const restored = await restoredPromise
      return {
        supported: true,
        lost,
        lostImmediately,
        restored,
        contextAliveAfterRestore: !context.isContextLost(),
        canvasInDom: document.contains(context.canvas),
      }
    })

    const facts = await readC3Facts(frame)
    const evidence = {
      kind: 'c3-webgl-restore',
      generatedAt: new Date().toISOString(),
      candidateCommit: process.env.C3_CANDIDATE_COMMIT ?? 'working-tree',
      outcome,
      after: { gl: facts.gl, media: facts.media, errorOverlay: facts.errorOverlay },
    }
    const evidencePath = await writeEvidence(testInfo, `webgl-restore-${suffix}`, evidence)
    testInfo.annotations.push({ type: 'evidence', description: evidencePath })
    console.log(`[c3-webgl] ${JSON.stringify(outcome)}`)

    expect(outcome.supported, `WebGL 演练无法执行：${'reason' in outcome ? outcome.reason : ''}`).toBe(true)
    // C3 接受两种结论：恢复成功，或页面给出明确错误；静默失效不算通过。
    const recovered = 'contextAliveAfterRestore' in outcome && outcome.contextAliveAfterRestore === true
    const explicitError = facts.errorOverlay
    expect(recovered || explicitError, '上下文丢失后既未恢复也没有明确错误').toBe(true)
  } finally {
    for (const pageId of createdPages) await archiveSandboxPage(api, pageId)
  }
})
