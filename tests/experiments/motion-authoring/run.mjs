// 文件功能：对四个原生 Vue SFC 样例做同题功能核对，记录错误与局部修改结果，不运行性能基准。
import assert from 'node:assert/strict'
import { readFile, writeFile, readdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createHash } from 'node:crypto'
import { chromium } from '@playwright/test'
import { prepare } from './environment.mjs'

/** 仅容忍 CSS 和对象数值序列化的小数差，不容忍错位的先后关系。 */
function near(actual, expected) { assert.ok(Math.abs(actual - expected) <= 0.001, `${actual} 应接近 ${expected}`) }
let browser, environment
const report = { date: new Date().toISOString(), scope: '原生库 Vue SFC 功能和作者审查；不含性能或独立模型评测', candidates: {} }
try {
  environment = await prepare(process.cwd()); report.versions = environment.versions; report.vueTypecheck = 'passed'
  report.sources = await Promise.all((await readdir(environment.source)).filter(name => /\.(vue|ts|mjs|css|html)$/.test(name)).sort().map(async name => ({ name, sha256: createHash('sha256').update(await readFile(resolve(environment.source, name))).digest('hex') })))
  browser = await chromium.launch({ headless: true })
  const page = await browser.newPage(), errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(environment.url)
  await page.waitForFunction(() => Boolean(window.authoring))
  for (const name of ['gsap', 'anime', 'motion', 'waapi']) {
    await page.evaluate(kind => window.authoring.mount(kind), name)
    const candidate = report.candidates[name] = { samples: [] }
    for (const time of [0, 200, 750, 1200, 3300]) {
      const direct = await page.evaluate(ms => window.authoring.sample(ms), time)
      await page.evaluate(() => window.authoring.sample(3400)); await page.evaluate(() => window.authoring.sample(0))
      const reverse = await page.evaluate(ms => window.authoring.sample(ms), time)
      assert.deepEqual(reverse, direct, `${name}: 乱序后状态应相同`)
      near(direct.durationMs, 3400); near(direct.untouchedRightModelMs, 0); near(direct.untouchedRightTitle, 0)
      candidate.samples.push({ time, state: direct })
    }
    near(candidate.samples[1].state.title, 0.5)
    candidate.samples[2].state.cards.forEach((opacity, i) => near(opacity, [0.5, 1 / 6, 0][i]))
    near(candidate.samples[3].state.modelMs, 300); near(candidate.samples[4].state.demo, 2 / 3)
    await page.evaluate(kind => window.authoring.mount(kind, 1400), name)
    const changed = await page.evaluate(() => window.authoring.sample(3300))
    near(changed.modelMs, 1900); near(changed.demo, 0); near(changed.durationMs, 3900)
    candidate.localEdit = { onlyInputChanged: 'detailStartMs: 900 → 1400', state: changed }
    candidate.cleanup = await page.evaluate(() => window.authoring.dispose())
    assert.equal(candidate.cleanup, 0)
    candidate.unmount = await page.evaluate(() => window.authoring.unmount())
    assert.deepEqual(candidate.unmount, { scenes: 0, nativeAnimations: 0 })
    console.log(`${name}: SFC、整体定位、乱序恢复、作用域隔离、局部延迟、清理通过`)
  }
  report.threeAdapters = await page.evaluate(() => window.authoring.probeAdapters())
  for (const adapter of Object.values(report.threeAdapters)) { near(adapter.x, 1); near(adapter.rotateYDegrees, 45) }
  await page.evaluate(() => window.authoring.mount('motion'))
  await page.locator('button').click()
  await page.waitForFunction(() => new DOMMatrix(getComputedStyle(document.querySelector('.interactive-card')).transform).m41 > 79.9)
  report.declarativeVue = await page.locator('.interactive-card').evaluate(element => {
    const matrix = new DOMMatrix(getComputedStyle(element).transform)
    return { x: matrix.m41, scale: matrix.m11 }
  })
  near(report.declarativeVue.x, 80); near(report.declarativeVue.scale, 1.1)
  await page.evaluate(() => window.authoring.unmount())
  assert.deepEqual(errors, []); report.status = 'passed'
} catch (error) {
  report.status = 'failed'; report.failure = error.stack
  if (error.stdout) report.typecheckOutput = String(error.stdout)
  console.error(report.typecheckOutput || error); process.exitCode = 1
} finally {
  await browser?.close(); await environment?.server.close()
  await writeFile(resolve('.tmp/motion-authoring/results.json'), `${JSON.stringify(report, null, 2)}\n`)
  console.log(JSON.stringify({ status: report.status, evidence: '.tmp/motion-authoring/results.json' }))
}
