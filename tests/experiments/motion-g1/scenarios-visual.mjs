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

export async function capture(page) {
  await mount(page, 'A13-capture')
  const defaults = await page.evaluate(() => window.__RUNTIME_APPLY_MOTION_SNAPSHOT__())
  assert.equal(defaults.sampledTimeMs, 800, '默认捕获应使用页面海报标签')
  assert.equal(defaults.status, 'applied')

  const atMs = await page.evaluate(() => window.__RUNTIME_APPLY_MOTION_SNAPSHOT__({ timelineId: 'capture', atMs: 500 }))
  const middle = await readStyle(page, '.title')
  assert.ok(middle.opacity > 0.2 && middle.opacity < 0.9, `500ms 应取到中间帧，实际 ${middle.opacity}`)
  assert.equal(atMs.sampledTimeMs, 500)
  assert.ok(atMs.planDigest && atMs.stateDigest, '回执必须包含计划与状态摘要')
  const firstFrame = `data:image/png;base64,${(await page.locator('.stage').screenshot()).toString('base64')}`

  const labelled = await page.evaluate(() => window.__RUNTIME_APPLY_MOTION_SNAPSHOT__({ timelineId: 'capture', atLabel: 'readable', offsetMs: 100 }))
  assert.equal(labelled.sampledTimeMs, 900)
  const tail = await readStyle(page, '.tail')
  assert.ok(tail.opacity > 0.7 && tail.opacity < 1, `标签偏移后收尾轨道应处于正确中间状态，实际 ${tail.opacity}`)

  const missing = await page.evaluate(async () => {
    try {
      await window.__RUNTIME_APPLY_MOTION_SNAPSHOT__({ timelineId: 'capture', atLabel: 'ghost' })
      return 'resolved'
    } catch (error) { return String(error?.message ?? error) }
  })
  assert.match(missing, /标签/, `不存在的标签必须明确失败，实际 ${missing}`)

  await page.evaluate(() => window.__RUNTIME_APPLY_MOTION_SNAPSHOT__({ timelineId: 'capture', atMs: 500 }))
  const frozen = await readStyle(page, '.title')
  const returnedFrame = `data:image/png;base64,${(await page.locator('.stage').screenshot()).toString('base64')}`
  const returnPixelDiff = await imageDiff(page, firstFrame, returnedFrame, 0)
  assert.ok(returnPixelDiff < 0.001, `乱序返回同一时刻应得到相同画面，差异 ${returnPixelDiff}`)
  await page.addStyleTag({ content: '*{animation:none!important;transition:none!important}' })
  await page.waitForTimeout(200)
  const afterDisable = await readStyle(page, '.title')
  const disabledFrame = `data:image/png;base64,${(await page.locator('.stage').screenshot()).toString('base64')}`
  const disabledPixelDiff = await imageDiff(page, returnedFrame, disabledFrame, 0)
  assert.ok(disabledPixelDiff < 0.001, `兜底禁动画不得改写固化画面，差异 ${disabledPixelDiff}`)
  assert.ok(Math.abs(afterDisable.opacity - frozen.opacity) < 0.01,
    `兜底禁动画不得改写已固化帧：${frozen.opacity} -> ${afterDisable.opacity}`)
  const media = await page.evaluate(() => ({
    paused: document.querySelector('video').paused,
    muted: document.querySelector('video').muted,
    time: document.querySelector('video').currentTime,
    seeking: document.querySelector('video').seeking,
  }))
  assert.equal(media.paused, true, '捕获不得播放媒体')

  return { defaults, atMs, labelled, frozen: frozen.opacity, afterDisable: afterDisable.opacity,
    returnPixelDiff, disabledPixelDiff, media, missing }
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
