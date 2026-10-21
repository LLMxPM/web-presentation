// 文件功能：启动回环随机端口的隔离 Vite，验证正式 motion 模块并保存浏览器证据。
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
import { chromium } from '@playwright/test'
import { encodeVideo } from '../motion-wp01/encode-video.mjs'

const source = fileURLToPath(new URL('.', import.meta.url))
const root = resolve(source, '../../..'), output = resolve(root, '.tmp/motion-fix-browser')
await mkdir(output, { recursive: true })
const require = createRequire(resolve(root, 'runtime/package.json'))
const { createServer } = await import(pathToFileURL(require.resolve('vite')).href)
const alias = { '@': resolve(root, 'runtime/src'), vue: require.resolve('vue/dist/vue.runtime.esm-bundler.js'), gsap: resolve(root, 'runtime/node_modules/gsap/index.js'), three: resolve(root, 'runtime/node_modules/three') }
const server = await createServer({ configFile: false, root: source, logLevel: 'error', resolve: { alias },
  plugins: [{ name: 'review-fixtures', configureServer(server) { server.middlewares.use(async (req, res, next) => {
    const files = { '/fixtures/clock.webm': '.tmp/motion-fix-browser/clock.webm', '/signatures.json': 'tests/fixtures/model-animation-signature-cases.json' }
    const file = files[req.url]
    if (!file) return next()
    const bytes = await readFile(resolve(root, file))
    res.setHeader('Content-Type', req.url.endsWith('webm') ? 'video/webm' : 'application/json')
    res.setHeader('Content-Length', bytes.length); res.end(bytes)
  }) } }], server: { host: '127.0.0.1', port: 0, fs: { allow: [root] } } })
let browser
try {
  await server.listen()
  browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ reducedMotion: 'reduce' })
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await encodeVideo(page, resolve(output, 'clock.webm'), chromium.executablePath())
  await page.goto(server.resolvedUrls.local[0])
  await page.waitForFunction(() => window.probe)
  await page.evaluate(async () => { await window.probe.ready; await window.probe.prepare() })
  const receipt = await page.evaluate(() => window.__RUNTIME_APPLY_MOTION_SNAPSHOT__({ timelineId: 'browser', atMs: 250, visualMode: 'full' }))
  const opacity = await page.locator('.title').evaluate(element => Number(getComputedStyle(element).opacity))
  assert.equal(opacity, 0.5)
  assert.equal(receipt.visualMode, 'full')
  await page.screenshot({ path: resolve(output, 'halfway.png') })
  await page.evaluate(() => window.probe.restart())
  await page.waitForTimeout(120)
  assert.equal(await page.locator('video').evaluate(video => video.paused), true)
  await page.waitForFunction(() => !document.querySelector('video').paused)
  await page.evaluate(() => window.probe.pause())
  const pausedAt = await page.locator('video').evaluate(video => video.currentTime)
  await page.waitForTimeout(150)
  assert.equal(await page.locator('video').evaluate(video => video.currentTime), pausedAt)
  await page.evaluate(() => window.probe.seek(450))
  assert.equal(await page.locator('video').evaluate(video => video.paused), true)
  await page.evaluate(() => window.probe.restart())
  try { await page.waitForFunction(() => window.probe.state.value.phase === 'completed', undefined, { timeout: 10000 }) }
  catch (error) { console.log(await page.evaluate(() => ({ state: window.probe.state.value, error: String(window.probe.error.value), video: { time: document.querySelector('video').currentTime, paused: document.querySelector('video').paused, seeking: document.querySelector('video').seeking, ready: document.querySelector('video').readyState } }))); throw error }
  assert.equal(await page.locator('video').evaluate(video => video.paused), true)
  const signatures = await page.evaluate(() => window.checkModelSignatures())
  signatures.forEach(value => assert.equal(value.actual, value.expected))
  await page.evaluate(() => window.unmountProbe())
  assert.equal(await page.locator('video').count(), 0)
  assert.deepEqual(errors, [])
  await writeFile(resolve(output, 'result.json'), JSON.stringify({ receipt, opacity, signatures, passed: true, browser: browser.version() }, null, 2))
  console.log(JSON.stringify({ passed: true, opacity, signatures: signatures.length, browser: browser.version() }))
} finally { await browser?.close(); await server.close() }
