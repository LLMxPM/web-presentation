// 文件功能：先封存 Luna 候选，再独立评分并输出有界反馈；不修改候选，不统计性能。
import { chromium } from '@playwright/test'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createHash } from 'node:crypto'
import assert from 'node:assert/strict'
import { prepare } from './environment.mjs'
import { installProbe } from './probe.mjs'
import { serve } from '../motion-wp01/server.mjs'
const options = Object.fromEntries(process.argv.slice(2).map(arg => arg.replace(/^--/, '').split('=')))
const { candidate, phase } = options, detail = Number(options.detail ?? 1200), callouts = options.callouts === 'true'
if (!/^(gsap|anime)-(native|builder)$/.test(candidate ?? '') || !/^[a-z][0-9]+$/.test(phase ?? '')) throw new Error('必须指定合法 --candidate 和 --phase')
const root = process.cwd(), directory = resolve(root, 'tests/experiments/motion-luna')
const evidence = resolve(directory, 'evidence', candidate, phase), output = resolve(root, '.tmp/motion-luna', candidate, phase)
const source = await readFile(resolve(directory, 'candidates', `${candidate}.vue`), 'utf8')
await mkdir(evidence, { recursive: true }); await mkdir(output, { recursive: true })
await writeFile(resolve(evidence, 'candidate.vue.txt'), source, { flag: 'wx' })
const sha = text => createHash('sha256').update(text).digest('hex')
const result = { candidate, phase, detail, callouts, requestedModel: 'gpt-6-luna', reasoningEffort: 'medium', sourceSha256: sha(source), inputs: {}, checks: {}, failures: [], samples: [] }
let environment, assets, browser
/** 同一字段只保留首个失败，给模型有界、无修复补丁的诊断。 */
function fail(code, fieldPath, expected, actual) {
  if (!result.failures.some(item => item.code === code && item.fieldPath === fieldPath)) result.failures.push({ code, fieldPath, expected, actual })
}
/** 线性属性同时检查可见值和位移，不能只对终点采样。 */
function checkStyle(actual, ms, start, duration, y, field) {
  const alpha = Math.min(1, Math.max(0, (ms - start) / duration)), targetY = y * (1 - alpha)
  if (Math.abs(actual.opacity - alpha) > 0.002) fail('VISUAL_OPACITY', field, { ms, opacity: +alpha.toFixed(5) }, actual)
  if (Math.abs(actual.y - targetY) > 0.03) fail('VISUAL_TRANSLATE_Y', field, { ms, y: +targetY.toFixed(4) }, actual)
}
/** 候选输出由固定夹具读取，调用过程中可启用真实回调探针。 */
const call = (page, method, ...args) => page.evaluate(async ({ method, args }) => window.lunaResearch[method](...args), { method, args })
try {
  for (const file of ['task.md', 'sdk.ts', 'BenchStage.vue', 'harness.ts', 'environment.mjs', 'evaluate.mjs', 'probe.mjs', 'protocol.json']) result.inputs[file] = sha(await readFile(resolve(directory, file)))
  // 候选不得越过资源桥接重复操作模型；这是职责检查，与样式断言分开记录。
  if (/assets\.model\.(sample|dispose)\s*\(/.test(source)) fail('RESOURCE_OWNERSHIP', 'visual', '仅控制 DOM 时间轴；模型由 transport 采样/释放', '候选直接调用 assets.model.sample/dispose')
  environment = await prepare(root, candidate, output); result.typecheck = environment.typecheck
  if (environment.typecheck.status !== 'passed') {
    fail('SFC_TYPECHECK_FAILED', 'script', '严格 Vue/TS 通过', environment.typecheck.output)
  } else {
    assets = await serve(resolve(root, '.tmp/motion-wp01/assets'), { protectedAssets: true, origin: new URL(environment.url).origin })
    browser = await chromium.launch({ headless: true, args: ['--mute-audio', '--autoplay-policy=no-user-gesture-required'] })
    result.browser = browser.version()
    const page = await browser.newPage({ viewport: { width: 940, height: 650 }, deviceScaleFactor: 1 })
    const pageErrors = []; page.on('pageerror', error => pageErrors.push(error.message))
    await page.goto(`${environment.url}?assets=${encodeURIComponent(assets.url)}`)
    await page.waitForFunction(() => Boolean(window.lunaResearch))
    await installProbe(page, candidate.split('-')[0], `/@fs/${resolve(root, '.tmp/motion-authoring/deps/node_modules').replaceAll('\\', '/')}`)
    const mounted = await call(page, 'mount', candidate)
    result.mount = mounted
    if (!mounted.ready) fail('PREPARE_FAILED', 'mount', 'ready', mounted.error)
    else {
      const untouched = await call(page, 'sample', 0)
      await page.evaluate(() => { window.lunaCallbackProbe.active = true; window.lunaCallbackProbe.events = [] })
      const points = [...new Set([0, 200, 750, 950, 1100, detail + 200, detail + 2400, detail + 4200, ...(callouts ? [detail + 150, detail + 270, detail + 390, detail + 2350, detail + 2470, detail + 2590] : [])])]
      for (const ms of points) {
        const sample = await call(page, 'sample', ms), { state, styles } = sample
        checkStyle(styles.title, ms, 0, 400, 32, 'title')
        styles.cards.forEach((card, i) => checkStyle(card, ms, 600 + i * 100, 300, 24, `card${i + 1}`))
        checkStyle(styles.clipCaption, ms, detail, 400, 0, 'clip-caption')
        checkStyle(styles.demoCaption, ms, detail + 2200, 400, 32, 'demo-caption')
        if (callouts) for (const [name, start] of [['calloutModel', detail + 100], ['calloutDemo', detail + 2300]]) styles[name].forEach((chip, i) => checkStyle(chip, ms, start + i * 80, 200, 12, `${name}.${i}`))
        if (state.durationMs !== detail + 4200) fail('PLAN_DURATION', 'durationMs', detail + 4200, state.durationMs)
        if (state.tracks.find(track => track.id === 'voice').endMs !== 4000) fail('VOICE_CHANGED', 'voice.endMs', 4000, state.tracks)
        const videoTime = 1000 + Math.min(2000, Math.max(0, ms - detail - 2200))
        if (Math.abs(state.video.ms - videoTime) > 1) fail('VIDEO_FRAME_TIME', 'video.ms', videoTime, state.video.ms)
        if (state.visiblePixels <= 0) fail('MODEL_INVISIBLE', 'model.pixels', '>0', state.visiblePixels)
        if (JSON.stringify(sample.rightStyles) !== JSON.stringify(untouched.rightStyles)) fail('SCOPE_LEAK', 'right.styles', untouched.rightStyles, sample.rightStyles)
        result.samples.push({ ms, styles, bones: state.bones, video: state.video, durationMs: state.durationMs })
      }
      const first = await call(page, 'sample', detail + 200)
      await call(page, 'sample', detail + 4200); await call(page, 'sample', 0)
      const restored = await call(page, 'sample', detail + 200)
      try { assert.deepEqual(restored, first); result.checks.reverseRestore = 'passed' } catch { fail('REVERSE_RESTORE', 'snapshot', first, restored) }
      result.callbackProbe = await page.evaluate(() => window.lunaCallbackProbe)
      if (!result.callbackProbe.timelines) fail('PROBE_NOT_REACHED', 'callbackProbe', '实际候选时间轴被探测', result.callbackProbe)
      if (result.callbackProbe.events.length) fail('VISUAL_CALLBACK_NOT_MUTED', 'sample', '任意 sample 不触发加入实际时间轴的计数回调', result.callbackProbe.events.slice(0, 8))
      const direct = await page.screenshot({ animations: 'allow' }); await call(page, 'freeze')
      const frozen = await page.screenshot({ animations: 'disabled' })
      if (!direct.equals(frozen)) fail('FREEZE_CAPTURE_CHANGED', 'freeze', 'PNG 相同', 'PNG 不同')
      else result.checks.freezeCapture = 'identical-png'
      const disposed = await call(page, 'dispose')
      result.checks.dispose = disposed.left.disposed && disposed.right.disposed && !disposed.left.rafActive && disposed.left.audio.paused && disposed.left.video.paused ? 'passed' : 'failed'
      if (result.checks.dispose !== 'passed') fail('DISPOSE_FAILED', 'dispose', '无播放者/自有 RAF', disposed)
      const stale = await call(page, 'mount', candidate, { badClip: true })
      result.checks.staleClip = stale.error?.code === 'MODEL_ANIMATION_REFERENCE_STALE' ? 'passed' : 'failed'
      if (result.checks.staleClip !== 'passed') fail('STALE_CLIP_NOT_REJECTED', 'clipRef', 'MODEL_ANIMATION_REFERENCE_STALE', stale)
    }
    await call(page, 'unmount'); result.pageErrors = pageErrors
    if (pageErrors.length) fail('BROWSER_ERROR', 'page', [], pageErrors)
  }
} catch (error) { fail('EVALUATOR_EXCEPTION', 'execution', '完成检查', error.stack) }
finally {
  await browser?.close(); await assets?.close(); await environment?.server?.close()
  result.status = result.failures.length ? 'failed' : 'passed'
  await writeFile(resolve(evidence, 'result.json'), `${JSON.stringify(result, null, 2)}\n`, { flag: 'wx' })
  console.log(JSON.stringify({ candidate, phase, status: result.status, feedback: result.failures.slice(0, 8) }))
  if (result.status === 'failed') process.exitCode = 1
}
