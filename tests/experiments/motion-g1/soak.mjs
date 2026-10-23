// 文件功能：在隔离 Chromium 中执行 G2 的 100 次页面进出与 30 分钟媒体循环，记录资源和时钟证据。
import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'

/** 从浏览器与 CDP 读取可比较的资源、时间轴和进程指标。 */
async function readMetrics(page, cdp, browserCdp) {
  await cdp.send('HeapProfiler.collectGarbage')
  const [heap, dom, processes, pageState] = await Promise.all([
    cdp.send('Runtime.getHeapUsage'),
    cdp.send('Memory.getDOMCounters'),
    browserCdp.send('SystemInfo.getProcessInfo'),
    page.evaluate(() => ({
      state: window.probe?.state?.value ?? null,
      media: Array.from(document.querySelectorAll('video,audio')).map(item => ({
        currentTime: item.currentTime, paused: item.paused, readyState: item.readyState,
      })),
      canvases: document.querySelectorAll('canvas').length,
      activeRaf: window.__motionSoak?.raf.size ?? 0,
      activeTimeouts: window.__motionSoak?.timeouts.size ?? 0,
      activeIntervals: window.__motionSoak?.intervals.size ?? 0,
      contextsCreated: window.__motionSoak?.contextsCreated ?? 0,
      liveContexts: (() => {
        const probe = window.__motionSoak
        if (!probe) return 0
        let count = 0
        probe.contexts = probe.contexts.filter(item => {
          const context = item.deref()
          if (!context || context.isContextLost()) return false
          count += 1
          return true
        })
        return count
      })(),
    })),
  ])
  return { at: new Date().toISOString(), heapUsedBytes: heap.usedSize,
    dom: { documents: dom.documents, nodes: dom.nodes, listeners: dom.jsEventListeners },
    processTypes: processes.processInfo.reduce((result, item) => {
      result[item.type] = (result[item.type] ?? 0) + 1
      return result
    }, {}), page: pageState }
}

/** 安装只计数不改变回调顺序的 RAF/计时器与 WebGL 上下文探针。 */
async function installResourceProbe(page) {
  await page.addInitScript(() => {
    const active = { raf: new Set(), timeouts: new Set(), intervals: new Set(), contexts: [], contextsCreated: 0 }
    window.__motionSoak = active
    const nativeRaf = window.requestAnimationFrame.bind(window)
    const nativeCancelRaf = window.cancelAnimationFrame.bind(window)
    window.requestAnimationFrame = callback => {
      const id = nativeRaf(time => { active.raf.delete(id); callback(time) })
      active.raf.add(id)
      return id
    }
    window.cancelAnimationFrame = id => { active.raf.delete(id); nativeCancelRaf(id) }
    const nativeTimeout = window.setTimeout.bind(window)
    const nativeClearTimeout = window.clearTimeout.bind(window)
    window.setTimeout = (handler, timeout, ...args) => {
      const id = nativeTimeout((...callbackArgs) => {
        active.timeouts.delete(id)
        if (typeof handler === 'function') handler(...callbackArgs)
      }, timeout, ...args)
      active.timeouts.add(id)
      return id
    }
    window.clearTimeout = id => { active.timeouts.delete(id); nativeClearTimeout(id) }
    const nativeInterval = window.setInterval.bind(window)
    const nativeClearInterval = window.clearInterval.bind(window)
    window.setInterval = (handler, timeout, ...args) => {
      const id = nativeInterval(handler, timeout, ...args)
      active.intervals.add(id)
      return id
    }
    window.clearInterval = id => { active.intervals.delete(id); nativeClearInterval(id) }
    const nativeContext = HTMLCanvasElement.prototype.getContext
    HTMLCanvasElement.prototype.getContext = function (...args) {
      const context = nativeContext.apply(this, args)
      if (context && (args[0] === 'webgl' || args[0] === 'webgl2' || args[0] === 'experimental-webgl')
        && !active.contexts.some(item => item.deref() === context)) {
        active.contextsCreated += 1
        active.contexts.push(new WeakRef(context))
      }
      return context
    }
  })
}

/** 完成 100 次真实双 GLB 挂载/卸载，再按固定节奏循环主媒体至目标时长。 */
export async function runSoak(browser, url, output, durationMs = 1_800_000) {
  const mountScenario = process.env.MOTION_SOAK_MOUNT_SCENARIO ?? 'A04-model-instances'
  const mountCycles = Number(process.env.MOTION_SOAK_MOUNT_CYCLES ?? 100)
  assert.ok(Number.isInteger(mountCycles) && mountCycles > 0, 'MOTION_SOAK_MOUNT_CYCLES 必须为正整数')
  const page = await browser.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await installResourceProbe(page)
  const cdp = await page.context().newCDPSession(page)
  const browserCdp = await browser.newBrowserCDPSession()
  const evidence = { browser: browser.version(), startedAt: new Date().toISOString(),
    runtimeMode: process.env.MOTION_RUNTIME_MODE ?? 'development', durationTargetMs: durationMs,
    mountCycles, mountScenario, modelsReadyBeforeUnmount: 0, metrics: [], errors }
  const save = () => writeFile(resolve(output, 'soak-result.json'), JSON.stringify(evidence, null, 2))
  try {
    await page.goto(url, { waitUntil: 'load' })
    await page.waitForFunction(() => Boolean(window.harness))
    evidence.metrics.push({ phase: 'baseline', ...await readMetrics(page, cdp, browserCdp) })
    for (let cycle = 1; cycle <= mountCycles; cycle += 1) {
      await page.evaluate(async scenario => {
        await window.harness.mount(scenario)
      }, mountScenario)
      if (mountScenario === 'A04-model-instances') {
        await page.waitForFunction(() => {
          const readyModels = document.querySelectorAll('[data-runtime-model-state="ready"]')
          return readyModels.length === 2
        }, undefined, { timeout: 40_000 })
        evidence.modelsReadyBeforeUnmount += 2
      }
      await page.evaluate(async () => {
        window.harness.unmount()
        window.probe = null
        // 等待卸载后的两个绘制机会，避免把尚未完成的 DOM/图形清理记成泄漏。
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
      })
      if (cycle % 10 === 0) {
        const sample = { phase: 'mount-unmount', cycle, ...await readMetrics(page, cdp, browserCdp) }
        evidence.metrics.push(sample)
        await save()
        console.log(`soak mount ${cycle}/${mountCycles} heap=${sample.heapUsedBytes} liveGL=${sample.page.liveContexts}`)
      }
    }
    const settleMs = Number(process.env.MOTION_SOAK_GC_SETTLE_MS ?? 0)
    if (settleMs > 0) {
      // 给 Chromium/GPU 进程异步回收 WebGL 包装对象的机会，再区分真实泄漏与延迟回收。
      await page.waitForTimeout(settleMs)
      await cdp.send('HeapProfiler.collectGarbage')
    }
    const cleanup = { phase: 'mount-cleanup', ...await readMetrics(page, cdp, browserCdp) }
    evidence.metrics.push(cleanup)
    await save()
    assert.equal(cleanup.page.canvases, 0, '100 次卸载后不得留下 WebGL canvas')
    assert.equal(cleanup.page.liveContexts, 0, '100 次卸载后不得留下活跃 WebGL 上下文')
    if (process.env.MOTION_SOAK_HEAP_SNAPSHOT === '1') {
      const chunks = []
      cdp.on('HeapProfiler.addHeapSnapshotChunk', event => chunks.push(event.chunk))
      await cdp.send('HeapProfiler.takeHeapSnapshot', { reportProgress: false })
      await writeFile(resolve(output, `heap-${mountScenario}.heapsnapshot`), chunks.join(''))
    }
    await page.evaluate(() => window.harness.mount('A06-media-clock'))
    const started = Date.now()
    let loop = 0
    let maxDriftMs = 0
    while (Date.now() - started < durationMs) {
      await page.evaluate(() => window.probe.restart())
      await page.waitForTimeout(1_000)
      const current = await page.evaluate(() => ({
        positionMs: window.probe.state.value?.positionMs ?? 0,
        mediaMs: (document.querySelector('video')?.currentTime ?? 0) * 1000,
      }))
      maxDriftMs = Math.max(maxDriftMs, Math.abs(current.positionMs - current.mediaMs))
      await page.waitForTimeout(2_150)
      loop += 1
      if (loop % 20 === 0 || Date.now() - started >= durationMs) {
        const sample = { phase: 'playback', loop, elapsedMs: Date.now() - started,
          driftMs: Math.abs(current.positionMs - current.mediaMs), ...await readMetrics(page, cdp, browserCdp) }
        evidence.metrics.push(sample)
        evidence.maxDriftMs = maxDriftMs
        await save()
        console.log(`soak playback ${Math.floor(sample.elapsedMs / 60000)}m loop=${loop} maxDrift=${maxDriftMs.toFixed(1)}ms`)
      }
    }
    evidence.elapsedMs = Date.now() - started
    evidence.playbackLoops = loop
    evidence.maxDriftMs = maxDriftMs
    await page.evaluate(() => {
      window.harness.unmount()
      window.probe = null
    })
    evidence.metrics.push({ phase: 'final-cleanup', ...await readMetrics(page, cdp, browserCdp) })
    assert.equal(evidence.metrics.at(-1).page.media.length, 0, '播放卸载后不得留下媒体元素')
    assert.equal(errors.length, 0, '长时循环不得出现未处理页面异常')
    assert.ok(evidence.elapsedMs >= durationMs, '长时循环必须达到目标时长')
    await save()
    return evidence
  } finally {
    await save()
    await browserCdp.detach()
    await cdp.detach()
    await page.close()
  }
}
