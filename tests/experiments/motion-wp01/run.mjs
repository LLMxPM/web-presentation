// 文件功能：执行 WP01 构建、跨域真实浏览器与八草案实验；输出原始证据并在 finally 回收本次进程。
import assert from 'node:assert/strict'
import { mkdir, writeFile, readFile, readdir } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { cpus, totalmem, platform, release } from 'node:os'
import { resolve } from 'node:path'
import { chromium } from '@playwright/test'
import { generateFixtures, fixtureManifest } from './fixtures.mjs'
import { encodeVideo } from './encode-video.mjs'
import { buildCandidates } from './build.mjs'
import { serve } from './server.mjs'
import { checkDrafts } from './drafts.mjs'
import { budgets } from './media.mjs'

const root = process.cwd(), output = resolve(root, '.tmp/motion-wp01'), assets = resolve(output, 'assets')
const sha = bytes => createHash('sha256').update(bytes).digest('hex')
/** 统计以原始样本为准的分位数，不对离群值删样或混入冷启动。 */
function stats(values) {
  const sorted = [...values].sort((a, b) => a - b)
  return { count: sorted.length, p95: sorted[Math.max(0, Math.ceil(sorted.length * 0.95) - 1)] ?? 0, max: sorted.at(-1) ?? 0 }
}

/** 在同一浏览器解码 PNG 后逐通道比较，区分编码变化、抗锯齿差异与真实状态漂移。 */
async function pixelDiff(page, left, right) {
  return page.evaluate(async encoded => {
    const buffers = await Promise.all(encoded.map(async value => {
      const bitmap = await createImageBitmap(await (await fetch(`data:image/png;base64,${value}`)).blob())
      const canvas = document.createElement('canvas'); canvas.width = bitmap.width; canvas.height = bitmap.height
      const ctx = canvas.getContext('2d'); ctx.drawImage(bitmap, 0, 0); bitmap.close()
      return ctx.getImageData(0, 0, canvas.width, canvas.height).data
    }))
    let changed = 0, beyond8 = 0, maxChannelDelta = 0
    for (let i = 0; i < buffers[0].length; i += 4) {
      let delta = 0
      for (let channel = 0; channel < 4; channel++) delta = Math.max(delta, Math.abs(buffers[0][i + channel] - buffers[1][i + channel]))
      if (delta) changed++; if (delta > 8) beyond8++
      maxChannelDelta = Math.max(maxChannelDelta, delta)
    }
    return { changedPixels: changed, beyond8Pixels: beyond8, totalPixels: buffers[0].length / 4, maxChannelDelta }
  }, [left.toString('base64'), right.toString('base64')])
}

let browser
const servers = [], result = { date: new Date().toISOString(), codeVersion: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(), device: { cpu: cpus()[0].model, logicalCpus: cpus().length, memoryGiB: +(totalmem() / 2 ** 30).toFixed(1), platform: platform(), release: release(), node: process.version }, viewport: { width: 960, height: 540, deviceScaleFactor: 1 }, engines: {} }
await mkdir(output, { recursive: true })
try {
  const sourceDirectory = resolve(root, 'tests/experiments/motion-wp01')
  result.sourceInputs = await Promise.all((await readdir(sourceDirectory)).filter(name => /\.(mjs|ps1)$/.test(name)).sort().map(async name => ({ name, sha256: sha(await readFile(resolve(sourceDirectory, name))) })))
  result.lockSha256 = sha(await readFile(resolve(root, 'pnpm-lock.yaml')))
  result.policy = { ...budgets, startupWindowMs: 250, maxTracks: 64, maxTargets: 32, maxDurationMs: 1800000, imageBeyond8Ratio: 0.001, gcGrowthLimitBytes: 1048576, narration: process.platform === 'win32' ? 'Microsoft Huihui Desktop 离线合成自有文案；补静音至四秒' : '提示音时钟替身；此平台不声称已验证中文语音' }
  await generateFixtures(assets)
  browser = await chromium.launch({ headless: true, args: ['--mute-audio', '--autoplay-policy=no-user-gesture-required', '--enable-precise-memory-info'] })
  result.browser = browser.version()
  const encoder = await browser.newPage()
  if (process.env.WP01_REUSE_VIDEO !== '1') await encodeVideo(encoder, resolve(assets, 'clock.webm'), chromium.executablePath())
  await encoder.close()
  result.fixtures = await fixtureManifest(assets)
  result.bundleSizes = await buildCandidates(root, output)
  result.drafts = checkDrafts()
  console.log(JSON.stringify({ phase: 'built', browser: result.browser, bundles: result.bundleSizes }))
  for (const name of ['waapi', 'gsap']) {
    const staticServer = await serve(resolve(output, name)); servers.push(staticServer)
    const assetServer = await serve(assets, { protectedAssets: true, origin: staticServer.url }); servers.push(assetServer)
    const context = await browser.newContext({ viewport: result.viewport, deviceScaleFactor: 1, reducedMotion: 'no-preference' })
    const page = await context.newPage(), errors = []
    page.on('pageerror', error => errors.push(error.message))
    // 仅允许两个本地静态源站。构建产物加载不读取 node_modules、不依赖 Vite，也不访问互联网。
    await page.route('**/*', route => [staticServer.url, assetServer.url].some(origin => route.request().url().startsWith(`${origin}/`)) ? route.continue() : route.abort())
    await page.goto(`${staticServer.url}/index.html?assets=${encodeURIComponent(assetServer.url)}`)
    const e = result.engines[name] = { init: await page.evaluate(() => window.spike.init()) }
    assert.ok(e.init.modelVisiblePixels > 1000, '三维实际画面必须可见，不能只检查骨骼数值')
    assert.equal(e.init.isolated, true); assert.equal(e.init.reduce, false)
    e.assetChecks = await page.evaluate(async assetUrl => {
      const denied = await fetch(`${assetUrl}/clock.webm`)
      const head = await fetch(`${assetUrl}/clock.webm?ticket=wp01-fixture`, { method: 'HEAD' })
      const range = await fetch(`${assetUrl}/clock.webm?ticket=wp01-fixture`, { headers: { Range: 'bytes=100-199' } })
      return { denied: denied.status, head: head.status, range: range.status, bytes: (await range.arrayBuffer()).byteLength }
    }, assetServer.url)
    assert.deepEqual(e.assetChecks, { denied: 403, head: 200, range: 206, bytes: 100 })
    e.negatives = await page.evaluate(() => window.spike.negatives())
    assert.equal(e.negatives.none.error, 'CLIP_NOT_FOUND'); assert.equal(e.negatives.missing.error, 'CLIP_TARGET_MISSING'); assert.equal(e.negatives.duplicate.clips, 2)
    e.samples = []
    for (const time of [325, 500, 1000, 1500]) {
      const direct = await page.evaluate(t => window.spike.sample(t), time)
      for (const t of [1900, 0, 900, 1800000]) {
        const intermediate = await page.evaluate(ms => window.spike.sample(ms), t)
        if (t === 1800000) assert.deepEqual(intermediate.model, [[0, 0, 0, 1], [0, 0, 0, 1]], '长时间定位必须得到精确片段终态，不能以终点前 epsilon 冒充末帧')
      }
      const reordered = await page.evaluate(t => window.spike.sample(t), time)
      assert.deepEqual(reordered, direct)
      e.samples.push(direct)
    }
    assert.notDeepEqual(e.samples[1].model[0], e.samples[1].model[1])
    await page.evaluate(() => window.spike.sample(325))
    const directPng = await page.screenshot()
    await page.evaluate(() => window.spike.sample(1500)); await page.evaluate(() => window.spike.sample(325))
    const reorderedPng = await page.screenshot()
    assert.ok(directPng.equals(reorderedPng), '乱序定位应生成同一像素 PNG')
    await writeFile(resolve(output, `${name}-325ms.png`), directPng)
    const frozenState = await page.evaluate(() => window.spike.freeze(325))
    assert.deepEqual(frozenState, e.samples[0], '样式固化不得改变规范状态')
    const frozenBefore = await page.screenshot()
    const frozenAfter = await page.screenshot({ animations: 'disabled' })
    await writeFile(resolve(output, `${name}-325ms-frozen.png`), frozenAfter)
    assert.ok(frozenBefore.equals(frozenAfter), '固化状态不能被禁动画截图改到终点')
    e.capture = { directSha256: sha(directPng), reorderedSha256: sha(reorderedPng), frozenSha256: sha(frozenAfter), exactPixels: true }
    e.capture.freezeDiff = await pixelDiff(page, directPng, frozenAfter)
    assert.ok(e.capture.freezeDiff.beyond8Pixels / e.capture.freezeDiff.totalPixels <= 0.001, '固化前后允许的抗锯齿差异不得超过千分之一像素')
    // 固化会取消后端对象；重建后继续播放测试。
    const devtools = await context.newCDPSession(page)
    e.cycleCounts = []; e.retainedWindows = []
    for (let batch = 0; batch < 5; batch++) {
      e.cycleCounts.push(...await page.evaluate(() => window.spike.cycles(20)))
      await devtools.send('HeapProfiler.collectGarbage')
      e.retainedWindows.push({ cycle: (batch + 1) * 20, heap: (await page.evaluate(() => window.spike.metrics())).heap, dom: await devtools.send('Memory.getDOMCounters') })
    }
    await devtools.detach()
    assert.ok(e.retainedWindows.at(-1).heap - e.retainedWindows[0].heap < 1024 * 1024, 'GC 后稳定窗口增长不应超过 1MiB')
    assert.ok(e.retainedWindows.at(-1).dom.nodes - e.retainedWindows[0].dom.nodes <= 2, '循环后 DOM 节点不能持续增长')
    assert.ok(e.cycleCounts.every(cycle => !cycle.raf && !cycle.animations && !cycle.players && !cycle.engine))
    e.heapBeforePlayback = (await page.evaluate(() => window.spike.metrics())).heap
    await page.evaluate(() => window.spike.play())
    await page.waitForFunction(() => window.spike.metrics().logicalMs >= 5400, { timeout: 10000 })
    await page.evaluate(() => window.spike.pause())
    e.metrics = await page.evaluate(() => window.spike.metrics())
    assert.ok(e.metrics.handoff, '旁白结束后必须转单调时钟继续')
    e.stats = { pauseMs: stats(e.metrics.pauses), warmSeekMs: stats(e.metrics.seeks), frameCostMs: stats(e.metrics.frameCosts), driftMs: stats(e.metrics.decodedFrames.filter(frame => frame.phase === 'steady').map(frame => Math.abs(frame.videoMs - frame.masterMs))), startupDriftMs: stats(e.metrics.decodedFrames.filter(frame => frame.phase === 'startup').map(frame => Math.abs(frame.videoMs - frame.masterMs))) }
    assert.ok(e.stats.driftMs.count >= 20, '必须有真实解码帧，不能空集合通过')
    assert.ok(e.stats.pauseMs.p95 <= 100); assert.ok(e.stats.warmSeekMs.p95 <= 1000)
    assert.ok(e.stats.driftMs.p95 <= 80 && e.stats.driftMs.max <= 160, '媒体稳态漂移超出 G0 候选预算')
    assert.ok(e.metrics.playbackWrites < 10, '媒体不允许每帧 seek')
    await page.emulateMedia({ reducedMotion: 'reduce' })
    e.reduced = await page.evaluate(() => window.spike.reduced())
    assert.deepEqual(e.reduced, { opacity: '1', reduced: true, mediaPaused: true })
    e.disposed = await page.evaluate(() => window.spike.dispose())
    assert.deepEqual(e.disposed, { raf: 0, decodedFrameId: 0, nativeAnimations: 0, engine: 0 })
    assert.deepEqual(errors, [])
    e.requests = assetServer.requests
    await context.close()
    console.log(JSON.stringify({ phase: 'verified', name, stats: e.stats, capture: e.capture }))
  }
  result.crossBackend = { opacityMaxDelta: 0, translateMaxDelta: 0 }
  result.engines.waapi.samples.forEach((left, index) => {
    const right = result.engines.gsap.samples[index]
    assert.deepEqual({ ...left, dom: undefined }, { ...right, dom: undefined })
    left.dom.forEach((values, target) => {
      result.crossBackend.opacityMaxDelta = Math.max(result.crossBackend.opacityMaxDelta, Math.abs(values[0] - right.dom[target][0]))
      result.crossBackend.translateMaxDelta = Math.max(result.crossBackend.translateMaxDelta, Math.abs(values[1] - right.dom[target][1]))
    })
  })
  // 跨引擎 CSS 序列化有末位舍入差；同后端的乱序状态仍使用上面的严格深比较。
  assert.ok(result.crossBackend.opacityMaxDelta <= 0.000101 && result.crossBackend.translateMaxDelta <= 0.001)
  assert.equal(result.engines.waapi.capture.directSha256, result.engines.gsap.capture.directSha256, '同设备同场景的两个后端截图必须一致')
  result.status = 'passed'
} catch (error) {
  result.status = 'failed'; result.failure = error.stack; console.error(error); process.exitCode = 1
} finally {
  await browser?.close()
  for (const server of servers.reverse()) await server.close()
  result.cleanedUp = { browserClosed: !browser?.isConnected(), serversClosed: true }
  // 原始 JSON 写入失败结果，便于复现，不把失败运行当成通过证据。
  await writeFile(resolve(output, 'results.json'), `${JSON.stringify(result, null, 2)}\n`)
  if (process.env.WP01_RUN_LABEL) {
    assert.match(process.env.WP01_RUN_LABEL, /^[a-z0-9-]+$/)
    await writeFile(resolve(output, `results-${process.env.WP01_RUN_LABEL}.json`), `${JSON.stringify(result, null, 2)}\n`)
  }
  console.log(JSON.stringify({ phase: 'complete', status: result.status, evidence: resolve(output, 'results.json') }))
}
