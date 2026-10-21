// 文件功能：运行含真实媒体与骨骼的六组合功能对照，不采集性能、体积或独立模型生成指标。
import { chromium } from '@playwright/test'
import { strict as assert } from 'node:assert'
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises'
import { resolve, relative } from 'node:path'
import { createHash } from 'node:crypto'
import { prepare } from './environment.mjs'
import { serve } from '../motion-wp01/server.mjs'
import { fixtureManifest } from '../motion-wp01/fixtures.mjs'

const root = process.cwd(), output = resolve(root, '.tmp/motion-story')
const results = { date: '2026-10-21', scope: '人工编写的完整 SFC 功能对照；不采集性能，非独立模型创作评测', cases: [], errors: {}, sourceHashes: {} }
let environment, assets, browser
/** 统一调用页面夹具，避免将 Playwright 控制逻辑混入被比较的 SFC。 */
const call = (page, method, ...args) => page.evaluate(async ({ method, args }) => window.storyResearch[method](...args), { method, args })
/** 只比较可见效果与解码内容；JSON 路线多出的轨道不影响比较目标。 */
const pixelsState = state => ({ title: state.title, cards: state.cards, clipCaption: state.clipCaption, demoCaption: state.demoCaption, bones: state.bones, videoPixels: state.video.pixels })
/** 验证实际媒体、骨骼及字幕，成功构建不能代替效果检查。 */
function inspect(state, ms, detail = 1200) {
  const model = state.tracks.find(track => track.id === 'model'), video = state.tracks.find(track => track.id === 'demo')
  assert.equal(model.startMs, detail); assert.equal(model.durationMs, 2000)
  assert.equal(video.startMs, detail + 2200); assert.equal(video.durationMs, 2000)
  assert.equal(state.durationMs, detail + 4200); assert.equal(state.logicalMs, ms)
  assert.equal(state.audio.paused, true); assert.equal(state.audio.muted, true)
  assert.equal(state.video.paused, true); assert.equal(state.video.muted, true)
  assert.ok(state.visiblePixels > 0); assert.equal(state.clip.name, 'wave'); assert.equal(state.clip.index, 0)
  assert.match(state.clip.signature, /^[0-9a-f]{64}$/)
  assert.ok(Math.abs(state.video.ms - (1000 + Math.min(2000, Math.max(0, ms - video.startMs)))) < 1)
  assert.ok(Math.abs(state.clipCaption - Math.min(1, Math.max(0, (ms - detail) / 400))) < 0.001)
  assert.ok(Math.abs(state.demoCaption - Math.min(1, Math.max(0, (ms - video.startMs) / 400))) < 0.001)
}
try {
  await mkdir(output, { recursive: true })
  environment = await prepare(root); results.versions = environment.versions; results.typecheck = 'passed'
  results.node = process.version
  results.lockSha256 = createHash('sha256').update(await readFile(resolve(root, 'pnpm-lock.yaml'))).digest('hex')
  results.fixtures = await fixtureManifest(resolve(root, '.tmp/motion-wp01/assets'))
  assets = await serve(resolve(root, '.tmp/motion-wp01/assets'), { protectedAssets: true, origin: new URL(environment.url).origin })
  browser = await chromium.launch({ headless: true, args: ['--mute-audio', '--autoplay-policy=no-user-gesture-required'] })
  const page = await browser.newPage({ viewport: { width: 940, height: 540 }, deviceScaleFactor: 1 })
  results.browser = browser.version()
  const pageErrors = []; page.on('pageerror', error => pageErrors.push(error.message))
  await page.goto(`${environment.url}?assets=${encodeURIComponent(assets.url)}`)
  await page.waitForFunction(() => Boolean(window.storyResearch))
  const baselines = new Map()
  for (const engine of ['gsap', 'anime']) for (const route of ['native', 'builder', 'json']) {
    const mounted = await call(page, 'mount', route, engine); assert.equal(mounted.ready, true, JSON.stringify(mounted))
    const record = { engine, route, samples: [] }
    for (const ms of [0, 1500, 3600, 5000]) {
      const state = await call(page, 'sample', ms); inspect(state, ms)
      if (ms === 1500) assert.notDeepEqual(state.bones[0], state.bones[1])
      const visible = pixelsState(state)
      if (!baselines.has(ms)) baselines.set(ms, visible); else assert.deepEqual(visible, baselines.get(ms))
      record.samples.push(state)
    }
    const first = await call(page, 'sample', 1500)
    await call(page, 'sample', 5400); await call(page, 'sample', 200)
    const restored = await call(page, 'sample', 1500); assert.deepEqual(restored, first)
    record.reverseRestore = 'passed'
    const direct = await page.screenshot({ animations: 'allow' })
    const frozen = await call(page, 'freeze'); assert.equal(frozen.rafActive, false)
    const captured = await page.screenshot({ animations: 'disabled' }); assert.ok(direct.equals(captured), `${engine}/${route}: 捕获像素不一致`)
    record.freezeCapture = 'identical-png'
    const disposed = await call(page, 'dispose'); assert.equal(disposed.disposed, true); assert.equal(disposed.rafActive, false)
    assert.equal(disposed.audio.paused, true); assert.equal(disposed.video.paused, true)
    record.dispose = 'passed'
    const edited = await call(page, 'mount', route, engine, { detailStartMs: 1700 }); assert.equal(edited.ready, true)
    const editState = await call(page, 'sample', 3900); inspect(editState, 3900, 1700)
    assert.equal(editState.tracks.find(track => track.id === 'voice').endMs, 4000)
    record.singleStartEdit = { detailMs: 1700, demoMs: 3900, durationMs: editState.durationMs, voiceEndMs: 4000 }
    const stale = await call(page, 'mount', route, engine, { badClip: true })
    assert.equal(stale.error.code, 'MODEL_ANIMATION_REFERENCE_STALE'); record.staleClipFeedback = stale.error
    const repaired = await call(page, 'mount', route, engine); assert.equal(repaired.ready, true)
    record.manualRepair = 'queried clipRef restored; ready'
    results.cases.push(record)
    console.log(JSON.stringify({ engine, route, status: 'passed' }))
  }
  results.errors = await call(page, 'errors')
  assert.equal(results.errors.target.code, 'TIMELINE_TARGET_INVALID')
  assert.equal(results.errors.cycle.code, 'TIMELINE_DEPENDENCY_CYCLE')
  assert.equal(results.errors.trim.code, 'TIMELINE_MEDIA_RANGE_INVALID')
  const noClip = await call(page, 'mount', 'native', 'gsap', { modelFile: 'none.glb' })
  assert.equal(noClip.error.code, 'CLIP_NOT_FOUND'); results.errors.noClip = noClip.error
  const missing = await call(page, 'mount', 'native', 'gsap', { modelFile: 'missing.glb' })
  assert.equal(missing.error.code, 'CLIP_TARGET_MISSING'); results.errors.missingTarget = missing.error
  const duplicate = await call(page, 'mount', 'native', 'anime', { modelFile: 'duplicate.glb' })
  assert.equal(duplicate.ready, true); assert.equal(duplicate.state.clip.index, 0)
  results.duplicateClip = { query: duplicate.state.clip, status: 'index 0 remains unambiguous when names duplicate' }
  results.livePlayback = []
  for (const engine of ['gsap', 'anime']) {
    await call(page, 'mount', 'native', engine); await call(page, 'play')
    await page.waitForFunction(() => { const s = window.storyResearch.state(); return s.playbackError || (!s.playing && !s.settling && s.logicalMs === s.durationMs) }, undefined, { timeout: 15000 })
    const finished = await call(page, 'state')
    assert.equal(finished.playbackError, null); assert.equal(finished.handoff, true); assert.equal(finished.logicalMs, 5400)
    assert.equal(finished.audio.paused, true); assert.equal(finished.video.paused, true); assert.equal(finished.rafActive, false)
    assert.equal(finished.video.ms, 3000); assert.equal(finished.settling, false)
    results.livePlayback.push({ engine, ...finished })
  }
  await call(page, 'mount', 'native', 'gsap'); await call(page, 'sample', 3600)
  await page.screenshot({ path: resolve(output, 'story-3600ms.png') })
  // 保留旧 DOM 引用检查卸载后的真实媒体，不能只检查新页面节点数量。
  await call(page, 'play')
  await page.waitForFunction(() => document.querySelector('audio').currentTime > 0.2)
  await page.evaluate(() => { window.retainedMedia = [...document.querySelectorAll('audio, video')] })
  const unmounted = await call(page, 'unmount')
  assert.deepEqual(unmounted, { roots: 0, animations: 0 })
  results.unmount = await page.evaluate(() => window.retainedMedia.map(media => ({ paused: media.paused, source: media.getAttribute('src') })))
  assert.ok(results.unmount.every(media => media.paused && media.source === null))
  assert.deepEqual(pageErrors, []); results.pageErrors = pageErrors
  results.mediaRequests = { protectedFixture: true, rangeResponses: assets.requests.filter(request => request.status === 206).length }
  results.status = 'passed'
} catch (error) { results.status = 'failed'; results.failure = error.stack; process.exitCode = 1 }
finally {
  await browser?.close(); await assets?.close(); await environment?.server.close()
  const sourceFiles = (await readdir(resolve(root, 'tests/experiments/motion-story'))).filter(name => /\.(ts|vue|mjs|css|html)$/.test(name)).map(file => resolve(root, 'tests/experiments/motion-story', file))
  const sharedFiles = ['media.mjs', 'model.mjs', 'server.mjs', 'fixtures.mjs', 'encode-video.mjs', 'narration.ps1'].map(file => resolve(root, 'tests/experiments/motion-wp01', file))
  for (const path of [...sourceFiles, ...sharedFiles]) {
    results.sourceHashes[relative(root, path).replaceAll('\\', '/')] = createHash('sha256').update(await readFile(path)).digest('hex')
  }
  await writeFile(resolve(output, 'results.json'), `${JSON.stringify(results, null, 2)}\n`)
  console.log(JSON.stringify({ status: results.status, cases: results.cases.length, failure: results.failure }))
}
