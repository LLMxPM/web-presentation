// 文件功能：启动隔离 Chromium 并汇总 G1 真实浏览器场景或 G2 长时循环的结果与证据。
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { tmpdir } from 'node:os'
import { execFileSync } from 'node:child_process'
import assert from 'node:assert/strict'
import { chromium } from '@playwright/test'
import { encodeVideo } from '../motion-wp01/encode-video.mjs'
import { buildSpinGlb, buildToneWav } from './fixtures.mjs'
import { domLayout, capture, modelInstances } from './scenarios-visual.mjs'
import { mediaClock, bufferPause, optionalFailure, secondaryBuffer, autoplayRefusal, seekHandover, audibleSeek, preference, mediaOwnership } from './scenarios-media.mjs'
import { runSoak } from './soak.mjs'
import { startMotionRuntimeServer } from './runtime-server.mjs'

const source = fileURLToPath(new URL('.', import.meta.url))
const root = resolve(source, '../../..')
const output = resolve(root, '.tmp/motion-g1')
await mkdir(output, { recursive: true })
const scratch = await mkdtemp(resolve(tmpdir(), 'motion-g1-'))

const sha = value => createHash('sha256').update(value).digest('hex')

const scenarios = [
  ['A03-dom-layout', domLayout],
  ['A06-media-clock', mediaClock],
  ['A07-buffer-pause', bufferPause],
  ['A07-secondary-buffer', secondaryBuffer],
  ['A07-optional-failure', optionalFailure],
  ['A08-autoplay', autoplayRefusal],
  ['A09-seek-handover', seekHandover],
  ['A09-audible-seek', audibleSeek],
  ['A13-capture', capture],
  ['A12-preference', preference],
  ['A10-media-ownership', mediaOwnership],
  ['A04-model-instances', modelInstances],
]

/** 失败时抓取最小现场，避免只凭错误文本猜原因。 */
async function diagnose(page) {
  return page.evaluate(() => ({
    state: window.probe?.state?.value ?? null,
    error: String(window.probe?.error?.value ?? ''),
    media: Array.from(document.querySelectorAll('video,audio')).map(element => ({
      tag: element.tagName.toLowerCase(),
      src: element.currentSrc || element.src,
      readyState: element.readyState,
      networkState: element.networkState,
      paused: element.paused,
      muted: element.muted,
      volume: element.volume,
      time: element.currentTime,
      duration: element.duration,
      error: element.error ? `${element.error.code}:${element.error.message}` : null,
    })),
    models: Array.from(document.querySelectorAll('[data-runtime-kit-media-kind="model3d"]')).map(element => ({
      className: element.className,
      assetName: element.getAttribute('data-runtime-asset-name'),
      state: element.getAttribute('data-runtime-model-state'),
      hasHandle: Boolean(element.__runtimeModelMotionHandleV1),
    })),
    canvases: document.querySelectorAll('canvas').length,
  }))
}

let browser
let runtimeServer
const results = {}
let fixtures = {}
try {
  browser = await chromium.launch({
    headless: true,
    // Playwright 默认注入 --autoplay-policy=no-user-gesture-required，会掩盖真实浏览器拒绝，
    // 这里移除默认值并显式要求用户手势，才能验证 blocked 与手势恢复。
    ignoreDefaultArgs: ['--autoplay-policy=no-user-gesture-required'],
    args: ['--autoplay-policy=document-user-activation-required', '--enable-unsafe-swiftshader'],
  })
  const setupPage = await browser.newPage()
  await encodeVideo(setupPage, resolve(scratch, 'clock.webm'), chromium.executablePath())
  await writeFile(resolve(scratch, 'tone.wav'), buildToneWav())
  await writeFile(resolve(scratch, 'spin.glb'), buildSpinGlb())
  await setupPage.close()
  fixtures = Object.fromEntries(await Promise.all(['clock.webm', 'tone.wav', 'spin.glb'].map(async name => [
    name, sha(await readFile(resolve(scratch, name))),
  ])))

  const mode = process.env.MOTION_RUNTIME_MODE ?? 'development'
  assert.ok(['development', 'production'].includes(mode), 'MOTION_RUNTIME_MODE 必须是 development 或 production')
  runtimeServer = await startMotionRuntimeServer({ mode, source, root, scratch })
  console.log(`motion-g1 runtime mode: ${mode} (${runtimeServer.url})`)

  if (process.argv[2] === '--soak') {
    const durationMs = Number(process.env.MOTION_SOAK_MS ?? 1_800_000)
    assert.ok(Number.isInteger(durationMs) && durationMs > 0, 'MOTION_SOAK_MS 必须为正整数')
    const startedAt = Date.now()
    try {
      const evidence = await runSoak(browser, runtimeServer.url, output, durationMs)
      results['G2-soak'] = { passed: true, durationMs: Date.now() - startedAt,
        mode, evidence: { mountScenario: evidence.mountScenario, mountCycles: evidence.mountCycles,
          modelsReadyBeforeUnmount: evidence.modelsReadyBeforeUnmount, playbackLoops: evidence.playbackLoops,
          elapsedMs: evidence.elapsedMs, maxDriftMs: evidence.maxDriftMs } }
    } catch (error) {
      results['G2-soak'] = { passed: false, durationMs: Date.now() - startedAt, error: String(error?.stack ?? error) }
    }
  }
  for (const [name, run] of process.argv[2] === '--soak' ? [] : scenarios) {
    if (process.argv[2] && !name.includes(process.argv[2])) continue
    const page = await browser.newPage()
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    const startedAt = Date.now()
    try {
      const url = name === 'A08-autoplay' ? `${runtimeServer.url}?autoplayProbe=1` : runtimeServer.url
      await page.goto(url, { waitUntil: 'load' })
      if (name !== 'A08-autoplay') await page.waitForFunction(() => Boolean(window.harness))
      const evidence = await run(page)
      assert.deepEqual(errors, [], `${name} 不应有未处理页面异常`)
      results[name] = { passed: true, durationMs: Date.now() - startedAt, evidence }
      await page.screenshot({ path: resolve(output, `${name}.png`) })
      console.log(`✓ ${name} (${Date.now() - startedAt}ms)`)
    } catch (error) {
      const snapshot = await diagnose(page).catch(() => null)
      results[name] = {
        passed: false,
        durationMs: Date.now() - startedAt,
        error: String(error?.message ?? error),
        pageErrors: errors,
        snapshot,
      }
      await page.screenshot({ path: resolve(output, `${name}-failed.png`) }).catch(() => {})
      console.error(`✗ ${name}: ${String(error?.message ?? error)}`)
      if (snapshot) console.error(JSON.stringify(snapshot))
    } finally {
      await page.close()
    }
  }
  const codeVersion = {
    head: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(),
    dirty: Boolean(execFileSync('git', ['status', '--short'], { cwd: root, encoding: 'utf8' }).trim()),
  }
  await writeFile(resolve(output, 'result.json'), JSON.stringify({
    codeVersion, mode, browser: browser.version(), platform: process.platform, arch: process.arch, fixtures, results,
  }, null, 2))
  const failed = Object.entries(results).filter(([, value]) => !value.passed).map(([name]) => name)
  console.log(JSON.stringify({ passed: failed.length === 0, scenarios: Object.keys(results), failed, browser: browser.version() }))
  if (failed.length) process.exitCode = 1
} finally {
  await browser?.close()
  await runtimeServer?.close()
  await rm(scratch, { recursive: true, force: true })
}
