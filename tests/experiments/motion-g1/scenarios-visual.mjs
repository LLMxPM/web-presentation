// 文件功能：验证 G1 DOM、指定状态捕获和双实例 WebGL 的真实画面。
import assert from 'node:assert/strict'
import { mount, readStyle, sample, imageDiff } from './scenario-common.mjs'

export async function domLayout(page) {
  await mount(page, 'A03-dom-layout')
  const stageBefore = await readStyle(page, '.stage')
  const titleBefore = await readStyle(page, '.title')
  const at0 = await sample(page, 0)
  const at250 = await page.evaluate(async () => { await window.probe.sampleAt(250); return window.harness.read('.steps') })
  const at300 = await sample(page, 300)
  const subAt300 = await readStyle(page, '.sub')
  const at600 = await sample(page, 600)
  const backTo300 = await sample(page, 300)
  const reduced = await page.evaluate(async () => { await window.probe.sampleAt(0, 'reduced'); return window.harness.read('.title') })
  const stageAfter = await readStyle(page, '.stage')

  assert.ok(at0.title.opacity < 0.05, `入场初态应为透明，实际 ${at0.title.opacity}`)
  assert.ok(at250.opacity < 0.05, `错峰轨道不得提前出现，实际 ${at250.opacity}`)
  assert.ok(at300.title.opacity > 0.2 && at300.title.opacity < 0.9, `300ms 应处于入场中，实际 ${at300.title.opacity}`)
  assert.ok(subAt300.opacity > 0.2, `并行轨道应同时可见，实际 ${subAt300.opacity}`)
  assert.ok(at600.title.opacity > 0.95, `结束时应可读，实际 ${at600.title.opacity}`)
  assert.ok(Math.abs(backTo300.title.opacity - at300.title.opacity) < 0.01, '乱序定位必须重建同一状态')
  assert.ok(reduced.opacity > 0.95, `reduced 必须直接可读，实际 ${reduced.opacity}`)
  assert.equal(at0.title.offsetTop, titleBefore.offsetTop, '变换不得改变布局位置')
  assert.equal(at300.title.offsetLeft, titleBefore.offsetLeft, '变换不得改变水平布局')
  const stageCenter = stageBefore.rect.x + stageBefore.rect.width / 2
  const titleCenter = at300.title.rect.x + at300.title.rect.width / 2
  assert.ok(Math.abs(stageCenter - titleCenter) < 1.5, `变换不得破坏外层居中：stage=${stageCenter} title=${titleCenter}`)
  assert.equal(stageAfter.rect.width, stageBefore.rect.width)

  return {
    opacity: { at0: at0.title.opacity, at250: at250.opacity, at300: at300.title.opacity, sub: subAt300.opacity, at600: at600.title.opacity, reduced: reduced.opacity },
    determinism: Math.abs(backTo300.title.opacity - at300.title.opacity),
    centeringDeltaPx: Math.abs(stageCenter - titleCenter),
    layout: { stageWidth: stageAfter.rect.width, titleOffsetTop: at0.title.offsetTop },
  }
}

export async function modelInstances(page) {
  // WebGL 默认不保留 drawing buffer；Playwright 元素截图读取已合成画面。
  const frames = async () => Promise.all([0, 1].map(async index => {
    const buffer = await page.locator('canvas').nth(index).screenshot()
    return `data:image/png;base64,${buffer.toString('base64')}`
  }))
  const ready = () => page.waitForFunction(() => document.querySelectorAll('[data-runtime-model-state="ready"]').length === 2, undefined, { timeout: 40000 })

  await mount(page, 'A04-model-instances', { bInMs: 600 })
  await ready()
  await page.evaluate(() => window.probe.sampleAt(500))
  await page.waitForTimeout(400)
  const first = await frames()
  assert.equal(first.length, 2, '应存在两个真实三维实例画布')
  const crossInstanceDiff = await imageDiff(page, first[0], first[1])
  assert.ok(crossInstanceDiff > 0.05, `两个实例同刻应呈现不同姿态，实际差异 ${crossInstanceDiff}`)

  await mount(page, 'A04-model-instances', { bInMs: 1000 })
  await ready()
  await page.evaluate(() => window.probe.sampleAt(500))
  await page.waitForTimeout(400)
  const second = await frames()
  const sameInstanceDiff = await imageDiff(page, first[0], second[0])
  const changedInstanceDiff = await imageDiff(page, first[1], second[1])
  assert.ok(sameInstanceDiff < 0.02, `未变实例不得被另一实例状态影响，实际差异 ${sameInstanceDiff}`)
  assert.ok(changedInstanceDiff > sameInstanceDiff + 0.01,
    `被改动实例应呈现新姿态，未变=${sameInstanceDiff}，改变=${changedInstanceDiff}`)

  await mount(page, 'A04-model-instances', { bInMs: 600, bCameraPosition: [3, 2, 4] })
  await ready()
  await page.evaluate(() => window.probe.sampleAt(500))
  await page.waitForTimeout(400)
  const cameraFrames = await frames()
  const cameraFirstDiff = await imageDiff(page, first[0], cameraFrames[0])
  const cameraSecondDiff = await imageDiff(page, first[1], cameraFrames[1])
  assert.ok(cameraFirstDiff < 0.02, `第二实例相机配置不得改动第一实例，差异 ${cameraFirstDiff}`)
  assert.ok(cameraSecondDiff > cameraFirstDiff + 0.02,
    `显式相机应只改变第二实例画面，差异 ${cameraSecondDiff}`)

  return { crossInstanceDiff, sameInstanceDiff, changedInstanceDiff, cameraFirstDiff, cameraSecondDiff }
}
