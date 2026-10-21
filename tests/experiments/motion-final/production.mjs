// 文件功能：真实裁剪依赖后加载 SFC、构建并在纯静态源站离线运行；这是 G0 原型而非完整产品镜像。
import assert from 'node:assert/strict'
import { chromium } from '@playwright/test'
import { access, mkdir, readFile, writeFile, realpath } from 'node:fs/promises'
import { resolve, relative } from 'node:path'
import { createHash } from 'node:crypto'
import { serveVite, viteConfig } from './environment.mjs'
import { checkCandidate, call } from './checks.mjs'
import { serveStatic } from './static.mjs'
import { serve } from '../motion-wp01/server.mjs'
const root = process.cwd(), directory = resolve('tests/experiments/motion-final')
const production = resolve('.tmp/motion-final/production'), output = resolve('.tmp/motion-final/delivery'), bundle = resolve(output, 'dist')
const protocol = JSON.parse(await readFile(resolve(directory, 'protocol.json'), 'utf8'))
const result = { scope: '真实 pnpm --prod 的最小 Runtime 执行依赖原型；不替代完整镜像/G1/G2', checks: {}, offline: [], inputs: {} }
const sha = bytes => createHash('sha256').update(bytes).digest('hex')
let environment, browser, staticServer, assetServer
try {
  await mkdir(output, { recursive: true })
  result.manifest = JSON.parse(await readFile(resolve(production, 'package.json'), 'utf8'))
  result.productionLockSha256 = sha(await readFile(resolve(production, 'pnpm-lock.yaml')))
  for (const name of ['vue-tsc']) {
    const present = await access(resolve(production, 'node_modules', name, 'package.json')).then(() => true, () => false)
    assert.equal(present, false, `${name} 不应出现在裁剪包中`)
  }
  result.checks.devDependenciesAbsent = ['vue-tsc']
  const typescript = JSON.parse(await readFile(resolve(production, 'node_modules/typescript/package.json'), 'utf8'))
  result.checks.typescriptPresentForSfcTypes = typescript.version
  environment = await serveVite(root, production)
  for (const [name, path] of Object.entries(environment.tools)) {
    const actual = await realpath(path)
    assert.ok(actual.toLowerCase().startsWith(production.toLowerCase() + '\\') || actual.startsWith(production + '/'), `${name} 实际来自裁剪包外`)
    result.checks[`${name}ResolvedInsideProduction`] = relative(production, actual).replaceAll('\\', '/')
  }
  browser = await chromium.launch({ headless: true, args: ['--mute-audio', '--autoplay-policy=no-user-gesture-required'] })
  result.browser = browser.version()
  assetServer = await serve(resolve('.tmp/motion-wp01/assets'), { protectedAssets: true, origin: new URL(environment.url).origin })
  const devPage = await browser.newPage({ viewport: { width: 940, height: 650 } })
  await devPage.goto(`${environment.url}?assets=${encodeURIComponent(assetServer.url)}`)
  await devPage.waitForFunction(() => Boolean(window.finalResearch))
  const loaded = await checkCandidate(devPage, 'a1', 1200)
  assert.deepEqual(loaded.failures, []); result.checks.prunedSfcLoad = 'passed'
  await devPage.close(); await assetServer.close(); assetServer = undefined
  await environment.server.close(); environment = undefined
  const { vite, config } = await viteConfig(root, production), modules = new Set()
  config.plugins.push({ name: 'motion-g0-input-audit', generateBundle(_options, chunks) {
    for (const chunk of Object.values(chunks)) if (chunk.type === 'chunk') for (const id of chunk.moduleIds) modules.add(id.replaceAll('\\', '/'))
  } })
  await vite.build({ ...config, build: { outDir: bundle, emptyOutDir: false, assetsDir: '', rollupOptions: { output: {
    entryFileNames: '[name]-[hash].js', chunkFileNames: '[name]-[hash].js', assetFileNames: '[name]-[hash][extname]',
  } } } })
  const dependencyModules = [...modules].filter(id => id.includes('/node_modules/'))
  assert.ok(dependencyModules.length > 0)
  assert.ok(dependencyModules.every(id => id.toLowerCase().includes(production.replaceAll('\\', '/').toLowerCase() + '/node_modules/')), '构建偷偷读取了工作区依赖')
  result.checks.bundleDependencySources = 'all library modules resolved inside pruned production directory'
  staticServer = await serveStatic(bundle)
  assetServer = await serve(resolve('.tmp/motion-wp01/assets'), { protectedAssets: true, origin: staticServer.url })
  const page = await browser.newPage({ viewport: { width: 940, height: 650 }, deviceScaleFactor: 1 })
  const errors = []; page.on('pageerror', error => errors.push(error.message))
  const forbidden = []
  await page.route('**/*', route => {
    const url = new URL(route.request().url())
    if (![staticServer.url, assetServer.url].includes(url.origin)) { forbidden.push(url.origin); return route.abort() }
    return route.continue()
  })
  await page.goto(`${staticServer.url}?assets=${encodeURIComponent(assetServer.url)}`)
  await page.waitForFunction(() => Boolean(window.finalResearch))
  for (const task of protocol.cases) {
    const checked = await checkCandidate(page, task.id, task.detail, task.callouts)
    assert.deepEqual(checked.failures, [], task.id)
    result.offline.push({ id: task.id, status: 'passed', checks: checked.checks })
  }
  assert.deepEqual(forbidden, []); assert.deepEqual(errors, [])
  result.checks.noExternalRequests = true; result.checks.noPageErrors = true
  await call(page, 'mount', 'c1'); await call(page, 'sample', 3600)
  await page.screenshot({ path: resolve(output, 'final-3600ms.png') })
  await call(page, 'mount', 'a1'); await call(page, 'play')
  await page.waitForFunction(() => { const s = window.finalResearch.state(); return s.playbackError || (!s.playing && !s.settling && s.logicalMs === s.durationMs) }, undefined, { timeout: 15000 })
  result.playback = await call(page, 'state')
  assert.equal(result.playback.playbackError, null); assert.equal(result.playback.handoff, true)
  assert.equal(result.playback.logicalMs, 5400); assert.equal(result.playback.video.ms, 3000)
  assert.equal(result.playback.audio.paused, true); assert.equal(result.playback.video.paused, true); assert.equal(result.playback.rafActive, false)
  result.checks.offlinePlaybackWithClockHandoff = 'passed'
  await call(page, 'play'); await page.waitForFunction(() => document.querySelector('audio').currentTime > 0.2)
  await page.evaluate(() => { window.retainedMedia = [...document.querySelectorAll('audio, video')] })
  assert.equal(await call(page, 'unmount'), 0)
  const released = await page.evaluate(() => window.retainedMedia.every(media => media.paused && media.getAttribute('src') === null))
  assert.equal(released, true); result.checks.playingUnmount = 'passed'
  assert.ok(staticServer.requests.every(file => /\.(html|js|css)$/.test(file)))
  result.staticFilesRequested = [...new Set(staticServer.requests)].sort()
  for (const file of ['production.mjs', 'environment.mjs', 'static.mjs', 'checks.mjs', 'prepare-production.mjs']) result.inputs[file] = sha(await readFile(resolve(directory, file)))
  result.status = 'passed'
} catch (error) { result.status = 'failed'; result.failure = error.stack; process.exitCode = 1 }
finally {
  await browser?.close(); await environment?.server?.close(); await staticServer?.close(); await assetServer?.close()
  await writeFile(resolve(directory, 'evidence/production.json'), `${JSON.stringify(result, null, 2)}\n`, { flag: 'wx' })
  console.log(JSON.stringify({ status: result.status, offlineCases: result.offline.length, checks: result.checks, failure: result.failure }))
}
