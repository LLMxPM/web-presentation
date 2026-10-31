/**
 * 文件功能：在真实项目预览中验证 Scene 正向播放、三种推进模式与静态产物一致性。
 * 放映配置只有 manual/timer/scene_end 与 completion_delay_ms；不提供任意时刻截图或媒体超时字段。
 * 真实发声、受保护慢速缓冲与观众窗口手势重试由 runtime-heavy/scene-joint.spec.ts 承接。
 */
import type { APIRequestContext } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { expect, test } from '../../fixtures/test-data'
import { countStrongRedPixels, decodePngPixels } from '../../helpers/png-pixels'
import { buildSceneAmbientPage, buildScenePage } from '../../helpers/scene-page-source'

/** 为沙箱项目写入 schema 4 放映配置；旧模式与旧预算字段一律不提交。 */
async function configureAdvance(
  api: APIRequestContext,
  projectId: number,
  mode: 'manual' | 'timer' | 'scene_end' = 'scene_end',
  delayMs = 5000,
  options: { loop?: boolean; completionDelayMs?: number } = {},
): Promise<void> {
  const response = await api.patch(`/api/projects/${projectId}`, {
    data: {
      slideshow: {
        transition: { effect: 'none', duration_ms: 0 },
        advance: { mode, delay_ms: delayMs, completion_delay_ms: options.completionDelayMs ?? 300 },
        loop: options.loop ?? false,
      },
    },
  })
  expect(response.ok(), await response.text()).toBeTruthy()
}

/** 创建临时页面并在用例结束后归档，避免污染沙箱项目路由。 */
async function createPage(api: APIRequestContext, sandbox: { workspaceId: number; projectId: number }, title: string, source: string): Promise<number> {
  const response = await api.post('/api/pages', {
    data: { workspace_id: sandbox.workspaceId, project_id: sandbox.projectId, title, file_type: 'vue', page_content: source },
  })
  expect(response.ok(), await response.text()).toBeTruthy()
  return Number((await response.json()).id)
}

/** 写入两条页面路由并返回可放映的预览地址。 */
async function publishTwoPages(api: APIRequestContext, projectId: number, firstPageId: number, secondPageId: number): Promise<string> {
  const routes = await api.put(`/api/projects/${projectId}/routes`, {
    data: { routes: [
      { route_type: 'page', route: 'scene', order: 0, hidden: false, page_id: firstPageId },
      { route_type: 'page', route: 'second', order: 1, hidden: false, page_id: secondPageId },
    ] },
  })
  expect(routes.ok(), await routes.text()).toBeTruthy()
  const artifact = await api.post(`/api/projects/${projectId}/preview-artifacts`, { data: {} })
  expect(artifact.ok(), await artifact.text()).toBeTruthy()
  return (await artifact.json()).preview_url as string
}

test('正式项目放映在有限任务实际完成后停留并推进一次', async ({ page, context, visualEditSandbox }) => {
  test.setTimeout(180_000)
  const api = context.request
  const { projectId } = visualEditSandbox
  const scenePageId = await createPage(api, visualEditSandbox, 'Scene 第一页', buildScenePage())
  try {
    await configureAdvance(api, projectId, 'scene_end', 5000, { completionDelayMs: 3000 })
    await page.goto(await publishTwoPages(api, projectId, scenePageId, visualEditSandbox.pageId))
    const runtime = page.frameLocator('iframe#preview')
    await expect(runtime.locator('.page-content-wrapper .scene-e2e-title')).toBeVisible()
    await runtime.getByRole('button', { name: '进入放映' }).click()
    const controls = runtime.getByRole('group', { name: '放映控制' })
    await expect(controls).toBeVisible()
    await expect(controls.locator('.runtime-playback-controls__page')).toHaveText('1 / 2')
    // scene_end 只等待实际完成，不用估计时长；完成后按 completion_delay_ms 停留。
    await expect(controls.locator('[data-testid="playback-remaining"]')).toHaveText('等待完成')
    await expect(runtime.locator('.page-content-wrapper .scene-e2e-counter')).toHaveText('100', { timeout: 20_000 })
    await expect(controls.locator('.runtime-playback-controls__page')).toHaveText('1 / 2')
    await expect(controls.locator('.runtime-playback-controls__page')).toHaveText('2 / 2', { timeout: 15_000 })
    await expect(runtime.locator('.page-content-wrapper').getByText(visualEditSandbox.pageTitle)).toBeVisible({ timeout: 15_000 })
    // 末页不循环，结束后继续停留。
    await page.waitForTimeout(1500)
    await expect(controls.locator('.runtime-playback-controls__page')).toHaveText('2 / 2')
  } finally {
    await api.patch(`/api/pages/${scenePageId}`, { data: { status: 'archived' } }).catch(() => undefined)
  }
})

test('无限 ambient 装饰不阻塞 scene_end 推进', async ({ page, context, visualEditSandbox }) => {
  test.setTimeout(180_000)
  const api = context.request
  const { projectId } = visualEditSandbox
  const scenePageId = await createPage(api, visualEditSandbox, 'Scene 装饰页', buildSceneAmbientPage())
  try {
    await configureAdvance(api, projectId, 'scene_end', 5000, { completionDelayMs: 300 })
    await page.goto(await publishTwoPages(api, projectId, scenePageId, visualEditSandbox.pageId))
    const runtime = page.frameLocator('iframe#preview')
    await runtime.getByRole('button', { name: '进入放映' }).click()
    const controls = runtime.getByRole('group', { name: '放映控制' })
    await expect(runtime.locator('.page-content-wrapper .scene-e2e-counter')).toHaveText('100', { timeout: 20_000 })
    // 装饰序列仍在无限重复，有限任务完成即推进。
    await expect(controls.locator('.runtime-playback-controls__page')).toHaveText('2 / 2', { timeout: 15_000 })
  } finally {
    await api.patch(`/api/pages/${scenePageId}`, { data: { status: 'archived' } }).catch(() => undefined)
  }
})

for (const mode of ['manual', 'timer', 'scene_end'] as const) {
  test(`Scene 页面沿用 ${mode} 放映推进语义`, async ({ page, context, visualEditSandbox }) => {
    test.setTimeout(120_000)
    const api = context.request
    const { projectId } = visualEditSandbox
    const update = await api.patch(`/api/pages/${visualEditSandbox.pageId}`, { data: { page_content: buildScenePage() } })
    expect(update.ok(), await update.text()).toBeTruthy()
    const secondPageId = await createPage(api, visualEditSandbox, `放映 ${mode} 第二页`,
      `<template><main class="scene-advance-second">放映 ${mode} 第二页</main></template>`)
    try {
      const routes = await api.put(`/api/projects/${projectId}/routes`, {
        data: { routes: [
          { route_type: 'page', route: 'scene', order: 0, hidden: false, page_id: visualEditSandbox.pageId },
          { route_type: 'page', route: 'second', order: 1, hidden: false, page_id: secondPageId },
        ] },
      })
      expect(routes.ok(), await routes.text()).toBeTruthy()
      // timer 到点即停止未完成任务；manual 与 scene_end 保留较长观察窗口，避免并行负载下越过整场放映。
      await configureAdvance(api, projectId, mode, mode === 'timer' ? 1000 : 5000, { completionDelayMs: 300 })
      const artifact = await api.post(`/api/projects/${projectId}/preview-artifacts`, { data: {} })
      expect(artifact.ok(), await artifact.text()).toBeTruthy()
      await page.goto((await artifact.json()).preview_url as string)
      const runtime = page.frameLocator('iframe#preview')
      await expect(runtime.locator('.page-content-wrapper .scene-e2e-title')).toBeVisible()
      await runtime.getByRole('button', { name: '进入放映' }).click()
      const controls = runtime.getByRole('group', { name: '放映控制' })
      await expect(controls.locator('.runtime-playback-controls__page')).toHaveText('1 / 2')
      if (mode === 'manual') {
        await expect(controls.locator('[data-testid="playback-remaining"]')).toHaveText('本页手动')
        await page.waitForTimeout(2500)
        await expect(controls.locator('.runtime-playback-controls__page')).toHaveText('1 / 2')
        await controls.getByRole('button', { name: '下一页' }).click()
      }
      await expect(runtime.locator('.page-content-wrapper .scene-advance-second')).toBeVisible({ timeout: 12_000 })
      await expect(controls.locator('.runtime-playback-controls__page')).toHaveText('2 / 2')
    } finally {
      await api.patch(`/api/pages/${secondPageId}`, { data: { status: 'archived' } }).catch(() => undefined)
    }
  })
}

test('已移除的指定状态截图字段返回校验错误', async ({ context, visualEditSandbox }) => {
  const response = await context.request.post(`/api/pages/${visualEditSandbox.pageId}/screenshot-jobs`, {
    data: { motion_snapshot: { timeline_id: 'e2e-advance', at_ms: 500, visual_mode: 'full' } },
  })
  expect(response.status()).toBe(422)
})

test('scene_end 页面没有有限 blocking 任务时明确报错', async ({ page, context, visualEditSandbox }) => {
  test.setTimeout(120_000)
  const api = context.request
  await configureAdvance(api, visualEditSandbox.projectId, 'scene_end')
  const artifact = await api.post(`/api/projects/${visualEditSandbox.projectId}/preview-artifacts`, { data: {} })
  expect(artifact.ok(), await artifact.text()).toBeTruthy()
  await page.goto((await artifact.json()).preview_url as string)
  const runtime = page.frameLocator('iframe#preview')
  await runtime.getByRole('button', { name: '进入放映' }).click()
  await expect(runtime.locator('.runtime-playback-error')).toContainText('scene_end 页面必须注册有限 blocking 任务')
  await expect(runtime.getByRole('group', { name: '放映控制' }).locator('.runtime-playback-controls__page')).toHaveText('1 / 1')
})

test('媒体目标缺失在正式放映界面显示有界错误', async ({ page, context, visualEditSandbox }) => {
  test.setTimeout(120_000)
  const api = context.request
  // 显式媒体任务点名不存在的目标：必须按真实失败处理，不能用时长估计伪造完成。
  const source = `<template><main ref="root" class="scene-media-error"><h1>媒体错误验收</h1></main></template>
<script setup lang="ts">
import { ref } from 'vue'
import { createSceneMediaTask } from '@runtime-kit/public/composables/media/createSceneMediaTask.v1'
import { usePageScene } from '@runtime-kit/public/composables/motion/usePageScene.v1'
import { useStaticPresentation } from '@runtime-kit/public/composables/static/useStaticPresentation.v1'
const root = ref<HTMLElement | null>(null)
useStaticPresentation({ root, mode: 'default' })
usePageScene({ root, define(scene) {
  scene.task(createSceneMediaTask({ id: 'narration', role: 'blocking', target: () => null }))
} })
</script>`
  const update = await api.patch(`/api/pages/${visualEditSandbox.pageId}`, { data: { page_content: source } })
  expect(update.ok(), await update.text()).toBeTruthy()
  await configureAdvance(api, visualEditSandbox.projectId, 'manual')
  const artifact = await api.post(`/api/projects/${visualEditSandbox.projectId}/preview-artifacts`, { data: {} })
  expect(artifact.ok(), await artifact.text()).toBeTruthy()
  await page.goto((await artifact.json()).preview_url as string)
  const runtime = page.frameLocator('iframe#preview')
  await runtime.getByRole('button', { name: '进入放映' }).click()
  const error = runtime.locator('.runtime-playback-error')
  await expect(error).toBeVisible({ timeout: 25_000 })
  await expect(error).toContainText('媒体')
  // 有界错误不泄露资源地址或浏览器堆栈。
  expect(await error.textContent()).not.toContain('http')
  await expect(runtime.getByRole('group', { name: '放映控制' }).locator('.runtime-playback-controls__page')).toHaveText('1 / 1')
})

test('保持当前页抑制自动推进，释放后继续', async ({ page, context, visualEditSandbox }) => {
  test.setTimeout(120_000)
  const api = context.request
  const { projectId } = visualEditSandbox
  const update = await api.patch(`/api/pages/${visualEditSandbox.pageId}`, { data: { page_content: buildScenePage() } })
  expect(update.ok(), await update.text()).toBeTruthy()
  const secondPageId = await createPage(api, visualEditSandbox, '保持第二页', '<template><main class="scene-hold-second">保持第二页</main></template>')
  try {
    const routes = await api.put(`/api/projects/${projectId}/routes`, {
      data: { routes: [
        { route_type: 'page', route: 'scene', order: 0, hidden: false, page_id: visualEditSandbox.pageId },
        { route_type: 'page', route: 'second', order: 1, hidden: false, page_id: secondPageId },
      ] },
    })
    expect(routes.ok(), await routes.text()).toBeTruthy()
    await configureAdvance(api, projectId, 'scene_end', 5000, { completionDelayMs: 300 })
    const artifact = await api.post(`/api/projects/${projectId}/preview-artifacts`, { data: {} })
    expect(artifact.ok(), await artifact.text()).toBeTruthy()
    await page.goto((await artifact.json()).preview_url as string)
    const runtime = page.frameLocator('iframe#preview')
    await runtime.getByRole('button', { name: '进入放映' }).click()
    const controls = runtime.getByRole('group', { name: '放映控制' })
    const hold = controls.locator('[data-testid="playback-hold-toggle"]')
    await hold.click()
    await expect(hold).toHaveAttribute('aria-pressed', 'true')
    await expect(controls.locator('[data-testid="playback-remaining"]')).toHaveText('保持当前页')
    await expect(runtime.locator('.page-content-wrapper .scene-e2e-counter')).toHaveText('100', { timeout: 20_000 })
    // 保持只抑制翻页，页内 Scene 继续播完。
    await page.waitForTimeout(2000)
    await expect(controls.locator('.runtime-playback-controls__page')).toHaveText('1 / 2')
    await hold.click()
    await expect(hold).toHaveAttribute('aria-pressed', 'false')
    await expect(controls.locator('.runtime-playback-controls__page')).toHaveText('2 / 2', { timeout: 15_000 })
  } finally {
    await api.patch(`/api/pages/${secondPageId}`, { data: { status: 'archived' } }).catch(() => undefined)
  }
})

test('Scene 页面独立构建后仍能播放和导出静态 PDF', async ({ page, context, visualEditSandbox }) => {
  test.setTimeout(360_000)
  const api = context.request
  const { projectId, pageId } = visualEditSandbox
  const update = await api.patch(`/api/pages/${pageId}`, { data: { page_content: buildScenePage() } })
  expect(update.ok(), await update.text()).toBeTruthy()
  await configureAdvance(api, projectId, 'manual')
  const created = await api.post(`/api/projects/${projectId}/build-jobs`, { data: {} })
  expect(created.ok(), await created.text()).toBeTruthy()
  const job = await created.json() as { id: number }
  await expect(async () => {
    const response = await api.get(`/api/build-jobs/${job.id}`)
    expect(response.ok()).toBeTruthy()
    const state = await response.json() as { status: string; error_message: string | null }
    expect(state.status, state.error_message ?? '').toBe('succeeded')
  }).toPass({ timeout: 240_000, intervals: [2_000] })
  const accessResponse = await api.post(`/api/projects/${projectId}/build-jobs/${job.id}/access`)
  expect(accessResponse.ok(), await accessResponse.text()).toBeTruthy()
  await page.goto((await accessResponse.json()).browse_url as string)
  const title = page.locator('.page-content-wrapper .scene-e2e-title')
  await expect(title).toBeVisible({ timeout: 30_000 })
  await page.getByRole('button', { name: '进入放映' }).click()
  const controls = page.getByRole('group', { name: '放映控制' })
  await expect(controls).toBeVisible()
  await expect(page.locator('.page-content-wrapper .scene-e2e-counter')).toHaveText('100', { timeout: 20_000 })
  await page.getByRole('button', { name: '退出放映' }).click()
  await page.locator('.nav-button--export').click()
  const dialog = page.locator('[role="dialog"][aria-labelledby="export-dialog-title"]')
  await dialog.getByText('截图PDF', { exact: true }).click()
  const downloadPromise = page.waitForEvent('download', { timeout: 120_000 })
  await dialog.getByRole('button', { name: '开始导出' }).click()
  const pdf = readFileSync((await (await downloadPromise).path()) as string)
  expect(pdf.subarray(0, 5).toString()).toBe('%PDF-')
})

for (const target of ['pptx', 'canvas-pdf'] as const) {
  test(`Scene 页面导出 ${target} 前后静态内容保持一致`, async ({ page, context, visualEditSandbox }) => {
    test.setTimeout(180_000)
    const api = context.request
    const update = await api.patch(`/api/pages/${visualEditSandbox.pageId}`, { data: { page_content: buildScenePage() } })
    expect(update.ok(), await update.text()).toBeTruthy()
    const artifact = await api.post(`/api/projects/${visualEditSandbox.projectId}/preview-artifacts`, { data: {} })
    expect(artifact.ok(), await artifact.text()).toBeTruthy()
    await page.goto((await artifact.json()).preview_url as string)
    const runtime = page.frameLocator('iframe#preview')
    const title = runtime.locator('.page-content-wrapper .scene-e2e-title')
    await expect(title).toBeVisible()
    // 未播放时静态模板完整可读，导出不触发 Scene 也不快进取帧。
    await expect.poll(() => title.evaluate(element => getComputedStyle(element).opacity)).toBe('1')
    await expect(runtime.locator('.page-content-wrapper .scene-e2e-counter')).toHaveText('0')
    const before = await title.screenshot()
    await runtime.locator('.nav-button--export').click()
    const dialog = runtime.locator('[role="dialog"][aria-labelledby="export-dialog-title"]')
    if (target === 'pptx') await expect(dialog.locator('input[value="pptx-editable"]')).toBeChecked()
    else await dialog.getByText('截图PDF', { exact: true }).click()
    await expect(dialog.locator(`input[value="${target === 'pptx' ? 'pptx-editable' : 'canvas-pdf'}"]`)).toBeChecked()
    const downloadPromise = page.waitForEvent('download', { timeout: 120_000 })
    await dialog.getByRole('button', { name: '开始导出' }).click()
    const download = await downloadPromise
    const bytes = readFileSync((await download.path()) as string)
    expect(download.suggestedFilename()).toMatch(target === 'pptx' ? /\.pptx$/ : /\.pdf$/)
    expect(bytes.byteLength).toBeGreaterThan(4096)
    expect(bytes.subarray(0, target === 'pptx' ? 4 : 5)).toEqual(
      target === 'pptx' ? Buffer.from([0x50, 0x4b, 0x03, 0x04]) : Buffer.from('%PDF-'),
    )
    if (target === 'pptx') expect(bytes.includes(Buffer.from('ppt/slides/slide1.xml'))).toBe(true)
    await dialog.getByRole('button', { name: '关闭', exact: true }).click()
    expect(await title.screenshot()).toEqual(before)
    await expect(runtime.locator('.page-content-wrapper .scene-e2e-counter')).toHaveText('0')
  })
}

test('远程 Renderer 为 Scene 页面生成可读静态默认态', async ({ context, visualEditSandbox }, testInfo) => {
  test.setTimeout(180_000)
  const api = context.request
  const update = await api.patch(`/api/pages/${visualEditSandbox.pageId}`, { data: { page_content: buildScenePage() } })
  expect(update.ok(), await update.text()).toBeTruthy()
  const jobResponse = await api.post(`/api/pages/${visualEditSandbox.pageId}/screenshot-jobs`, { data: {} })
  expect(jobResponse.ok(), await jobResponse.text()).toBeTruthy()
  const jobId = Number((await jobResponse.json()).id)
  await expect.poll(async () => {
    const response = await api.get(`/api/pages/screenshot-jobs/${jobId}`)
    expect(response.ok()).toBeTruthy()
    const status = await response.json() as { status: string; error_code: string | null }
    return { status: status.status, error: status.error_code }
  }, { timeout: 120_000, intervals: [1_000, 2_000] }).toEqual({ status: 'succeeded', error: null })
  const detailResponse = await api.get(`/api/pages/${visualEditSandbox.pageId}`)
  expect(detailResponse.ok()).toBeTruthy()
  const imageResponse = await api.get((await detailResponse.json()).screenshot_url as string)
  expect(imageResponse.ok()).toBeTruthy()
  const png = Buffer.from(await imageResponse.body())
  await testInfo.attach('scene-static-remote.png', { body: png, contentType: 'image/png' })
  const decoded = decodePngPixels(png)
  const redPixels = countStrongRedPixels(decoded)
  expect(redPixels / (decoded.width * decoded.height), `静态默认态红色标题像素=${redPixels}`).toBeGreaterThan(0.001)
})
