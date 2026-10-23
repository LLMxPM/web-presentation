/**
 * 文件功能：在真实项目预览中验证页内时间轴推进，以及关闭的指定状态截图能力。
 */
import type { APIRequestContext } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { expect, test } from '../../fixtures/test-data'
import { countStrongRedPixels, decodePngPixels } from '../../helpers/png-pixels'
import { buildMotionPage } from '../../helpers/motion-page-source'
import { shortWavDataUri } from '../../helpers/motion-media'

/** 为沙箱项目配置放映推进方式，保留完整放映 DTO。 */
async function configureAdvance(
  api: APIRequestContext,
  projectId: number,
  mode: 'manual' | 'timer' | 'media_end' | 'timeline_end' = 'timeline_end',
  delayMs = 5000,
  loop = false,
): Promise<void> {
  const response = await api.patch(`/api/projects/${projectId}`, {
    data: {
      slideshow: {
        transition: { effect: 'none', duration_ms: 0 },
        advance: { mode, delay_ms: delayMs, media_timeout_ms: 300000, timeline_timeout_ms: 10000 },
        loop,
        auto_start: true,
      },
    },
  })
  expect(response.ok(), await response.text()).toBeTruthy()
}

test('正式项目放映在时间轴结束后推进一次', async ({ page, context, visualEditSandbox }) => {
  test.setTimeout(180_000)
  const api = context.request
  const { workspaceId, projectId } = visualEditSandbox
  const motionResponse = await api.post('/api/pages', {
    data: {
      workspace_id: workspaceId,
      project_id: projectId,
      title: '时间轴第一页',
      file_type: 'vue',
      page_content: buildMotionPage(),
    },
  })
  expect(motionResponse.ok(), await motionResponse.text()).toBeTruthy()
  const motionPage = (await motionResponse.json()) as { id: number }
  try {
    const routesResponse = await api.put(`/api/projects/${projectId}/routes`, {
      data: { routes: [
        { route_type: 'page', route: 'motion', order: 0, hidden: false, page_id: motionPage.id },
        { route_type: 'page', route: 'home', order: 1, hidden: false, page_id: visualEditSandbox.pageId },
      ] },
    })
    expect(routesResponse.ok(), await routesResponse.text()).toBeTruthy()
    await configureAdvance(api, projectId)
    const artifactResponse = await api.post(`/api/projects/${projectId}/preview-artifacts`, { data: {} })
    expect(artifactResponse.ok(), await artifactResponse.text()).toBeTruthy()
    const artifact = await artifactResponse.json() as { preview_url: string }
    await page.goto(artifact.preview_url)
    const runtime = page.frameLocator('iframe#preview')
    await expect(runtime.locator('.page-content-wrapper .motion-e2e-title')).toBeVisible()
    await runtime.getByRole('button', { name: '进入放映' }).click()
    await expect(runtime.getByRole('group', { name: '放映控制' })).toBeVisible()
    await expect(runtime.locator('.page-content-wrapper .motion-e2e-title')).toBeVisible()
    await page.waitForTimeout(450)
    await expect(runtime.locator('.page-content-wrapper .motion-e2e-title')).toBeVisible()
    await expect(runtime.locator('.page-content-wrapper').getByText(visualEditSandbox.pageTitle)).toBeVisible({ timeout: 15000 })
    await expect(runtime.getByRole('group', { name: '放映控制' }).locator('.runtime-playback-controls__page')).toHaveText('2 / 2')
    await page.waitForTimeout(1000)
    await expect(runtime.getByRole('group', { name: '放映控制' }).locator('.runtime-playback-controls__page')).toHaveText('2 / 2')
  } finally {
    await api.patch(`/api/pages/${motionPage.id}`, { data: { status: 'archived' } }).catch(() => undefined)
  }
})

for (const mode of ['manual', 'timer', 'media_end'] as const) {
  test(`时间轴页面沿用 ${mode} 放映推进语义`, async ({ page, context, visualEditSandbox }) => {
    test.setTimeout(120_000)
    const api = context.request
    const motionResponse = await api.patch(`/api/pages/${visualEditSandbox.pageId}`, {
      data: { page_content: buildMotionPage() },
    })
    expect(motionResponse.ok(), await motionResponse.text()).toBeTruthy()
    const secondResponse = await api.post('/api/pages', {
      data: {
        workspace_id: visualEditSandbox.workspaceId,
        project_id: visualEditSandbox.projectId,
        title: `放映 ${mode} 第二页`,
        file_type: 'vue',
        page_content: `<template><main class="motion-advance-second">放映 ${mode} 第二页</main></template>`,
      },
    })
    expect(secondResponse.ok(), await secondResponse.text()).toBeTruthy()
    const secondPage = await secondResponse.json() as { id: number }
    try {
      const routeResponse = await api.put(`/api/projects/${visualEditSandbox.projectId}/routes`, {
        data: { routes: [
          { route_type: 'page', route: 'motion', order: 0, hidden: false, page_id: visualEditSandbox.pageId },
          { route_type: 'page', route: 'second', order: 1, hidden: false, page_id: secondPage.id },
        ] },
      })
      expect(routeResponse.ok(), await routeResponse.text()).toBeTruthy()
      // timer 的第二页也会自动结束；保留观察窗口，避免并行 E2E 负载下越过整场放映。
      await configureAdvance(api, visualEditSandbox.projectId, mode, mode === 'timer' ? 5000 : 1000)
      const artifactResponse = await api.post(`/api/projects/${visualEditSandbox.projectId}/preview-artifacts`, { data: {} })
      expect(artifactResponse.ok(), await artifactResponse.text()).toBeTruthy()
      const artifact = await artifactResponse.json() as { preview_url: string }
      await page.goto(artifact.preview_url)
      const runtime = page.frameLocator('iframe#preview')
      await expect(runtime.locator('.page-content-wrapper .motion-e2e-title')).toBeVisible()
      await runtime.getByRole('button', { name: '进入放映' }).click()
      const controls = runtime.getByRole('group', { name: '放映控制' })
      await expect(controls.locator('.runtime-playback-controls__page')).toHaveText('1 / 2')
      if (mode === 'manual') {
        await page.waitForTimeout(2500)
        await expect(controls.locator('.runtime-playback-controls__page')).toHaveText('1 / 2')
        await controls.getByRole('button', { name: '下一页' }).click()
      }
      await expect(runtime.locator('.page-content-wrapper .motion-advance-second')).toBeVisible({ timeout: 12000 })
      await expect(controls.locator('.runtime-playback-controls__page')).toHaveText('2 / 2')
    } finally {
      await api.patch(`/api/pages/${secondPage.id}`, { data: { status: 'archived' } }).catch(() => undefined)
    }
  })
}

test('真实媒体结束后推进，双页循环重新进入媒体页', async ({ page, context, visualEditSandbox }) => {
  test.setTimeout(120_000)
  const api = context.request
  const source = `<template><main class="motion-media-loop"><h1>有声页</h1><audio data-runtime-media-purpose="narration" muted src="${shortWavDataUri()}"></audio></main></template>`
  const update = await api.patch(`/api/pages/${visualEditSandbox.pageId}`, { data: { page_content: source } })
  expect(update.ok(), await update.text()).toBeTruthy()
  const secondResponse = await api.post('/api/pages', {
    data: {
      workspace_id: visualEditSandbox.workspaceId,
      project_id: visualEditSandbox.projectId,
      title: '媒体循环第二页',
      file_type: 'vue',
      page_content: '<template><main class="motion-media-loop-second">媒体循环第二页</main></template>',
    },
  })
  expect(secondResponse.ok(), await secondResponse.text()).toBeTruthy()
  const second = await secondResponse.json() as { id: number }
  try {
    const routes = await api.put(`/api/projects/${visualEditSandbox.projectId}/routes`, {
      data: { routes: [
        { route_type: 'page', route: 'media', order: 0, hidden: false, page_id: visualEditSandbox.pageId },
        { route_type: 'page', route: 'second', order: 1, hidden: false, page_id: second.id },
      ] },
    })
    expect(routes.ok(), await routes.text()).toBeTruthy()
    await configureAdvance(api, visualEditSandbox.projectId, 'media_end', 1200, true)
    const artifactResponse = await api.post(`/api/projects/${visualEditSandbox.projectId}/preview-artifacts`, { data: {} })
    expect(artifactResponse.ok(), await artifactResponse.text()).toBeTruthy()
    const artifact = await artifactResponse.json() as { preview_url: string }
    await page.goto(artifact.preview_url)
    const runtime = page.frameLocator('iframe#preview')
    await runtime.getByRole('button', { name: '进入放映' }).click()
    const controls = runtime.getByRole('group', { name: '放映控制' })
    await expect(controls.locator('.runtime-playback-controls__page')).toHaveText('1 / 2')
    await expect(runtime.locator('.page-content-wrapper .motion-media-loop audio')).toHaveJSProperty('ended', false)
    await expect(controls.locator('.runtime-playback-controls__page')).toHaveText('2 / 2', { timeout: 10_000 })
    await expect(runtime.locator('.page-content-wrapper .motion-media-loop-second')).toBeVisible()
    await expect(controls.locator('.runtime-playback-controls__page')).toHaveText('1 / 2', { timeout: 10_000 })
    await expect(runtime.locator('.page-content-wrapper .motion-media-loop audio')).toHaveJSProperty('ended', false)
    await expect(controls.locator('.runtime-playback-controls__page')).toHaveText('2 / 2', { timeout: 10_000 })
  } finally {
    await api.patch(`/api/pages/${second.id}`, { data: { status: 'archived' } }).catch(() => undefined)
  }
})

test('指定状态截图能力关闭时返回明确错误', async ({ context, visualEditSandbox }) => {
  const response = await context.request.post(`/api/pages/${visualEditSandbox.pageId}/screenshot-jobs`, {
    data: { motion_snapshot: { timeline_id: 'e2e-advance', at_ms: 500, visual_mode: 'full' } },
  })
  expect(response.status()).toBe(409)
  const body = await response.json() as { code: string }
  expect(body.code).toBe('TIMELINE_UNSUPPORTED')
})

test('没有时间轴的放映页明确报错', async ({ page, context, visualEditSandbox }) => {
  test.setTimeout(120_000)
  const api = context.request
  await configureAdvance(api, visualEditSandbox.projectId)
  const artifactResponse = await api.post(`/api/projects/${visualEditSandbox.projectId}/preview-artifacts`, { data: {} })
  expect(artifactResponse.ok(), await artifactResponse.text()).toBeTruthy()
  const artifact = await artifactResponse.json() as { preview_url: string }
  await page.goto(artifact.preview_url)
  const runtime = page.frameLocator('iframe#preview')
  await runtime.getByRole('button', { name: '进入放映' }).click()
  await expect(runtime.locator('.runtime-playback-error')).toContainText('没有可执行时间轴')
  await expect(runtime.getByRole('group', { name: '放映控制' }).locator('.runtime-playback-controls__page')).toHaveText('1 / 1')
})

test('必需媒体加载失败在正式放映界面显示有界错误', async ({ page, context, visualEditSandbox }) => {
  test.setTimeout(120_000)
  const brokenPage = `<template><main ref="root"><audio class="motion-broken-audio" src="data:audio/wav;base64,AA=="></audio><h1>媒体错误验收</h1></main></template>
<script setup lang="ts">
import { ref } from 'vue'
import { usePageTimeline } from '@runtime-kit/public/composables/motion/usePageTimeline.v1'
const root = ref<HTMLElement | null>(null)
usePageTimeline({ root, bindings: {}, applyPoster: false, definition: {
  schemaVersion: 1, timelineId: 'e2e-media-error',
  tracks: [{ type: 'audio', id: 'voice', asset: 'broken', selector: '.motion-broken-audio', outMs: 1000, role: 'primary' }],
} })
</script>`
  const update = await context.request.patch(`/api/pages/${visualEditSandbox.pageId}`, {
    data: { page_content: brokenPage },
  })
  expect(update.ok(), await update.text()).toBeTruthy()
  await configureAdvance(context.request, visualEditSandbox.projectId, 'manual')
  const artifactResponse = await context.request.post(`/api/projects/${visualEditSandbox.projectId}/preview-artifacts`, { data: {} })
  expect(artifactResponse.ok(), await artifactResponse.text()).toBeTruthy()
  const artifact = await artifactResponse.json() as { preview_url: string }
  await page.goto(artifact.preview_url)
  const runtime = page.frameLocator('iframe#preview')
  await runtime.getByRole('button', { name: '进入放映' }).click()
  await expect(runtime.locator('.runtime-playback-error')).toBeVisible({ timeout: 25_000 })
  await expect(runtime.locator('.runtime-playback-error')).toContainText(/媒体|加载|解码/)
  await expect(runtime.getByRole('group', { name: '放映控制' }).locator('.runtime-playback-controls__page')).toHaveText('1 / 1')
})

test('必需媒体持续无响应在正式放映界面显示超时', async ({ page, context, visualEditSandbox }) => {
  test.setTimeout(120_000)
  const source = `<template><main ref="root"><audio class="motion-stalled-audio" preload="none" src="/motion-stall.wav"></audio><h1>媒体超时验收</h1></main></template>
<script setup lang="ts">
import { ref } from 'vue'
import { usePageTimeline } from '@runtime-kit/public/composables/motion/usePageTimeline.v1'
const root = ref<HTMLElement | null>(null)
usePageTimeline({ root, bindings: {}, applyPoster: false, definition: {
  schemaVersion: 1, timelineId: 'e2e-media-timeout',
  tracks: [{ type: 'audio', id: 'voice', asset: 'stalled', selector: '.motion-stalled-audio', outMs: 1000, role: 'primary' }],
} })
</script>`
  const update = await context.request.patch(`/api/pages/${visualEditSandbox.pageId}`, {
    data: { page_content: source },
  })
  expect(update.ok(), await update.text()).toBeTruthy()
  await configureAdvance(context.request, visualEditSandbox.projectId, 'manual')
  const artifactResponse = await context.request.post(`/api/projects/${visualEditSandbox.projectId}/preview-artifacts`, { data: {} })
  expect(artifactResponse.ok(), await artifactResponse.text()).toBeTruthy()
  const artifact = await artifactResponse.json() as { preview_url: string }
  await page.route('**/motion-stall.wav', async route => {
    await new Promise(resolve => setTimeout(resolve, 22_000))
    await route.abort()
  })
  await page.goto(artifact.preview_url, { waitUntil: 'domcontentloaded' })
  const runtime = page.frameLocator('iframe#preview')
  await runtime.getByRole('button', { name: '进入放映' }).click()
  await expect(runtime.locator('.runtime-playback-error')).toContainText('超时', { timeout: 25_000 })
  await expect(runtime.getByRole('group', { name: '放映控制' }).locator('.runtime-playback-controls__page')).toHaveText('1 / 1')
})

test('时间轴页面独立构建后仍能播放和导出静态 PDF', async ({ page, context, visualEditSandbox }) => {
  test.setTimeout(360_000)
  const api = context.request
  const { projectId, pageId } = visualEditSandbox
  const update = await api.patch(`/api/pages/${pageId}`, { data: { page_content: buildMotionPage() } })
  expect(update.ok(), await update.text()).toBeTruthy()
  await configureAdvance(api, projectId, 'manual')
  const created = await api.post(`/api/projects/${projectId}/build-jobs`, { data: {} })
  expect(created.ok(), await created.text()).toBeTruthy()
  const job = await created.json() as { id: number; status: string }
  await expect(async () => {
    const response = await api.get(`/api/build-jobs/${job.id}`)
    expect(response.ok()).toBeTruthy()
    const state = await response.json() as { status: string; error_message: string | null }
    expect(state.status, state.error_message ?? '').toBe('succeeded')
  }).toPass({ timeout: 240_000, intervals: [2_000] })
  const accessResponse = await api.post(`/api/projects/${projectId}/build-jobs/${job.id}/access`)
  expect(accessResponse.ok(), await accessResponse.text()).toBeTruthy()
  const access = await accessResponse.json() as { browse_url: string }
  await page.goto(access.browse_url)
  const title = page.locator('.page-content-wrapper .motion-e2e-title')
  await expect(title).toBeVisible({ timeout: 30_000 })
  await page.getByRole('button', { name: '进入放映' }).click()
  await expect(page.getByRole('group', { name: '放映控制' })).toBeVisible()
  await expect.poll(() => title.evaluate(element => getComputedStyle(element).opacity), { timeout: 10_000 }).toBe('1')
  await page.getByRole('button', { name: '退出放映' }).click()
  await page.locator('.nav-button--export').click()
  const dialog = page.locator('[role="dialog"][aria-labelledby="export-dialog-title"]')
  await dialog.getByText('截图PDF', { exact: true }).click()
  const downloadPromise = page.waitForEvent('download', { timeout: 120_000 })
  await dialog.getByRole('button', { name: '开始导出' }).click()
  const download = await downloadPromise
  const pdf = readFileSync((await download.path()) as string)
  expect(pdf.subarray(0, 5).toString()).toBe('%PDF-')
})

test('时间轴页面导出 PPTX 后仍保持静态海报', async ({ page, context, visualEditSandbox }) => {
  test.setTimeout(180_000)
  const api = context.request
  const updateResponse = await api.patch(`/api/pages/${visualEditSandbox.pageId}`, {
    data: { page_content: buildMotionPage() },
  })
  expect(updateResponse.ok(), await updateResponse.text()).toBeTruthy()
  const artifactResponse = await api.post(`/api/projects/${visualEditSandbox.projectId}/preview-artifacts`, { data: {} })
  expect(artifactResponse.ok(), await artifactResponse.text()).toBeTruthy()
  const artifact = await artifactResponse.json() as { preview_url: string }
  await page.goto(artifact.preview_url)
  const runtime = page.frameLocator('iframe#preview')
  const title = runtime.locator('.page-content-wrapper .motion-e2e-title')
  await expect(title).toBeVisible()
  await expect.poll(() => title.evaluate(element => getComputedStyle(element).opacity)).toBe('1')
  const before = await title.screenshot()
  await runtime.locator('.nav-button--export').click()
  const dialog = runtime.locator('[role="dialog"][aria-labelledby="export-dialog-title"]')
  await expect(dialog.locator('input[value="pptx-editable"]')).toBeChecked()
  const downloadPromise = page.waitForEvent('download', { timeout: 120_000 })
  await dialog.getByRole('button', { name: '开始导出' }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toMatch(/\.pptx$/)
  const pptx = readFileSync((await download.path()) as string)
  expect(pptx.byteLength).toBeGreaterThan(4096)
  expect(pptx.subarray(0, 4)).toEqual(Buffer.from([0x50, 0x4b, 0x03, 0x04]))
  expect(pptx.includes(Buffer.from('ppt/slides/slide1.xml'))).toBe(true)
  await dialog.getByRole('button', { name: '关闭', exact: true }).click()
  const after = await title.screenshot()
  expect(after).toEqual(before)
})

test('时间轴页面导出截图 PDF 后仍保持静态海报', async ({ page, context, visualEditSandbox }) => {
  test.setTimeout(180_000)
  const api = context.request
  const updateResponse = await api.patch(`/api/pages/${visualEditSandbox.pageId}`, {
    data: { page_content: buildMotionPage() },
  })
  expect(updateResponse.ok(), await updateResponse.text()).toBeTruthy()
  const artifactResponse = await api.post(`/api/projects/${visualEditSandbox.projectId}/preview-artifacts`, { data: {} })
  expect(artifactResponse.ok(), await artifactResponse.text()).toBeTruthy()
  const artifact = await artifactResponse.json() as { preview_url: string }
  await page.goto(artifact.preview_url)
  const runtime = page.frameLocator('iframe#preview')
  const title = runtime.locator('.page-content-wrapper .motion-e2e-title')
  await expect(title).toBeVisible()
  await expect.poll(() => title.evaluate(element => getComputedStyle(element).opacity)).toBe('1')
  const before = await title.screenshot()
  await runtime.locator('.nav-button--export').click()
  const dialog = runtime.locator('[role="dialog"][aria-labelledby="export-dialog-title"]')
  await dialog.getByText('截图PDF', { exact: true }).click()
  await expect(dialog.locator('input[value="canvas-pdf"]')).toBeChecked()
  const downloadPromise = page.waitForEvent('download', { timeout: 120_000 })
  await dialog.getByRole('button', { name: '开始导出' }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toMatch(/\.pdf$/)
  const pdf = readFileSync((await download.path()) as string)
  expect(pdf.byteLength).toBeGreaterThan(4096)
  expect(pdf.subarray(0, 5).toString('ascii')).toBe('%PDF-')
  await dialog.getByRole('button', { name: '关闭', exact: true }).click()
  const after = await title.screenshot()
  expect(after).toEqual(before)
})

test('远程 Renderer 为时间轴页面生成可见静态海报', async ({ context, visualEditSandbox }, testInfo) => {
  test.setTimeout(180_000)
  const api = context.request
  const updateResponse = await api.patch(`/api/pages/${visualEditSandbox.pageId}`, {
    data: { page_content: buildMotionPage() },
  })
  expect(updateResponse.ok(), await updateResponse.text()).toBeTruthy()
  const jobResponse = await api.post(`/api/pages/${visualEditSandbox.pageId}/screenshot-jobs`, { data: {} })
  expect(jobResponse.ok(), await jobResponse.text()).toBeTruthy()
  const job = await jobResponse.json() as { id: number }
  await expect.poll(async () => {
    const response = await api.get(`/api/pages/screenshot-jobs/${job.id}`)
    expect(response.ok()).toBeTruthy()
    const status = await response.json() as { status: string; error_code: string | null }
    return { status: status.status, error: status.error_code }
  }, { timeout: 120_000, intervals: [1000, 2000] }).toEqual({ status: 'succeeded', error: null })
  const detailResponse = await api.get(`/api/pages/${visualEditSandbox.pageId}`)
  expect(detailResponse.ok()).toBeTruthy()
  const detail = await detailResponse.json() as { screenshot_url: string }
  const imageResponse = await api.get(detail.screenshot_url)
  expect(imageResponse.ok()).toBeTruthy()
  const png = Buffer.from(await imageResponse.body())
  await testInfo.attach('motion-poster-remote.png', { body: png, contentType: 'image/png' })
  const decoded = decodePngPixels(png)
  const redPixels = countStrongRedPixels(decoded)
  expect(redPixels / (decoded.width * decoded.height), `海报红色标题像素=${redPixels}`).toBeGreaterThan(0.001)
})
