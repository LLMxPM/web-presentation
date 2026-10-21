// 文件功能：复用 WP01 最终静态包，注入 400ms 视频偏差并在播放中销毁，单独验证异常校正与回收。
import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '@playwright/test'
import { serve } from '../server.mjs'

const output = resolve('.tmp/motion-wp01')
const result = { scenario: '视频人为前移400ms后恢复；播放中dispose', browser: '', sourceSha256: createHash('sha256').update(await readFile(fileURLToPath(import.meta.url))).digest('hex'), engines: {} }
const servers = []
let browser
try {
  browser = await chromium.launch({ headless: true, args: ['--mute-audio', '--autoplay-policy=no-user-gesture-required'] })
  result.browser = browser.version()
  for (const name of ['waapi', 'gsap']) {
    const host = await serve(resolve(output, name)); servers.push(host)
    const assets = await serve(resolve(output, 'assets'), { protectedAssets: true, origin: host.url }); servers.push(assets)
    const context = await browser.newContext({ viewport: { width: 960, height: 540 }, deviceScaleFactor: 1, reducedMotion: 'no-preference' })
    const page = await context.newPage()
    await page.goto(`${host.url}/index.html?assets=${encodeURIComponent(assets.url)}`)
    await page.evaluate(() => window.spike.init())
    await page.evaluate(() => window.spike.play())
    await page.waitForFunction(() => window.spike.metrics().logicalMs >= 500)
    const injected = await page.evaluate(() => {
      const voice = document.querySelector('#voice'), video = document.querySelector('#video')
      video.currentTime = 1 + voice.currentTime + 0.4
      return { masterMs: voice.currentTime * 1000, sourceTargetMs: video.currentTime * 1000, now: performance.now() }
    })
    await page.waitForFunction(() => window.spike.metrics().corrections >= 1, null, { timeout: 1500 })
    const recoveryMs = await page.evaluate(now => performance.now() - now, injected.now)
    await page.waitForFunction(() => window.spike.metrics().logicalMs >= 1500, null, { timeout: 3000 })
    const metrics = await page.evaluate(() => window.spike.metrics())
    const tail = metrics.decodedFrames.filter(frame => frame.phase === 'steady').slice(-8)
    assert.equal(tail.length, 8)
    const tailMaxDriftMs = Math.max(...tail.map(frame => Math.abs(frame.videoMs - frame.masterMs)))
    assert.ok(tailMaxDriftMs <= 80, '注入异常后恢复稳态预算')
    assert.ok(metrics.corrections >= 1 && metrics.corrections <= 4, '必须发生有界校正，不能进入每帧seek循环')
    assert.ok(metrics.raf > 0 && metrics.mediaPlaying > 0, '必须在实际播放中测试dispose')
    const disposed = await page.evaluate(() => window.spike.dispose())
    assert.deepEqual(disposed, { raf: 0, decodedFrameId: 0, nativeAnimations: 0, engine: 0 })
    const stopped = await page.evaluate(() => window.spike.metrics().logicalMs)
    await page.waitForTimeout(80)
    const after = await page.evaluate(() => window.spike.metrics())
    assert.equal(after.logicalMs, stopped); assert.equal(after.mediaPlaying, 0)
    result.engines[name] = { injected, recoveryMs, tailMaxDriftMs, corrections: metrics.corrections, tail, disposed, remainsStoppedMs: 80 }
    await context.close()
  }
  result.status = 'passed'
} catch (error) {
  result.status = 'failed'; result.failure = error.stack; process.exitCode = 1
} finally {
  await browser?.close()
  for (const server of servers.reverse()) await server.close()
  result.cleanedUp = { browserClosed: !browser?.isConnected(), serversClosed: true }
  await writeFile(resolve(output, 'correction-probe.json'), `${JSON.stringify(result, null, 2)}\n`)
  console.log(JSON.stringify(result))
}
