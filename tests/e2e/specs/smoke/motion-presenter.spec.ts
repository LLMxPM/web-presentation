/**
 * 文件功能：用真实双窗口 Chromium 验证演讲控制台与唯一观众窗口的联动。
 */
import { expect, test } from '../../fixtures/test-data'

test('演讲模式复用观众窗口并同步翻页', async ({ page, context, visualEditSandbox }) => {
  test.setTimeout(180_000)
  const api = context.request
  const secondResponse = await api.post('/api/pages', {
    data: {
      workspace_id: visualEditSandbox.workspaceId,
      project_id: visualEditSandbox.projectId,
      title: '演讲第二页',
      file_type: 'vue',
      page_content: '<template><main class="presenter-e2e-second">演讲第二页</main></template>',
    },
  })
  expect(secondResponse.ok(), await secondResponse.text()).toBeTruthy()
  const secondPage = await secondResponse.json() as { id: number }
  try {
    const routeResponse = await api.put(`/api/projects/${visualEditSandbox.projectId}/routes`, {
      data: { routes: [
        { route_type: 'page', route: 'home', order: 0, hidden: false, page_id: visualEditSandbox.pageId },
        { route_type: 'page', route: 'second', order: 1, hidden: false, page_id: secondPage.id },
      ] },
    })
    expect(routeResponse.ok(), await routeResponse.text()).toBeTruthy()
    const artifactResponse = await api.post(`/api/projects/${visualEditSandbox.projectId}/preview-artifacts`, { data: {} })
    expect(artifactResponse.ok(), await artifactResponse.text()).toBeTruthy()
    const artifact = await artifactResponse.json() as { preview_url: string }
    await page.goto(artifact.preview_url)
    const runtime = page.frameLocator('iframe#preview')
    await expect(runtime.locator('.nav-button--presenter')).toBeVisible()
    const popupPromise = page.waitForEvent('popup')
    await runtime.locator('.nav-button--presenter').click()
    const display = await popupPromise
    await expect(runtime.locator('.presenter-console')).toBeVisible()
    await expect(display.locator('.presenter-display-screen')).toBeVisible()
    await expect(runtime.locator('.presenter-console')).toHaveAttribute('data-runtime-execution', 'thumbnail')
    await expect(display.locator('.presenter-display-screen')).toHaveAttribute('data-runtime-execution', 'presentation')

    await display.getByRole('button', { name: '当前窗口全屏' }).click()
    await expect(runtime.locator('.presenter-console__display-status')).toContainText('全屏中')
    const transport = runtime.getByRole('region', { name: '观众放映状态' })
    await transport.getByRole('button', { name: '下一页' }).click()
    await expect(display.locator('.presenter-e2e-second')).toBeVisible()
    await expect(runtime.locator('[data-testid="presenter-playback-page"]')).toHaveText('2 / 2')

    await display.evaluate(() => {
      const key = Object.keys(localStorage).find(item => item.startsWith('web-presentation.presenter.sync.'))
      if (!key) throw new Error('缺少控制台同步消息')
      const stored = JSON.parse(localStorage.getItem(key) ?? '{}') as { message: Record<string, unknown> }
      const base = stored.message
      const channel = new BroadcastChannel(`web-presentation:presenter:${String(base.channelId)}`)
      const navigate = {
        ...base, type: 'navigate', currentPath: '/home', sourceId: 'g1-old-console',
        revision: 9999, playback: base.playback,
      }
      channel.postMessage({ ...navigate, protocol: 3, eventId: 'g1-old-protocol' })
      channel.postMessage({ ...navigate, protocol: 4, ownerEpoch: 0, eventId: 'g1-old-owner' })
      channel.close()
    })
    await page.waitForTimeout(400)
    await expect(display.locator('.presenter-e2e-second')).toBeVisible()
    await expect(runtime.locator('[data-testid="presenter-playback-page"]')).toHaveText('2 / 2')

    const before = context.pages().length
    await runtime.getByRole('button', { name: '观众窗口', exact: true }).click()
    await expect(display.locator('.presenter-e2e-second')).toBeVisible()
    expect(context.pages().length).toBe(before)

    await display.close()
    expect(context.pages().length).toBe(before - 1)
    const reopenedPromise = page.waitForEvent('popup')
    await runtime.getByRole('button', { name: '观众窗口', exact: true }).click()
    const reopened = await reopenedPromise
    await expect(reopened.locator('.presenter-e2e-second')).toBeVisible()
    expect(context.pages().length).toBe(before)
    await reopened.getByRole('button', { name: '当前窗口全屏' }).click()
    await expect(runtime.locator('.presenter-console__display-status')).toContainText('全屏中')

    const previewElement = await page.locator('iframe#preview').elementHandle()
    const previewFrame = await previewElement?.contentFrame()
    expect(previewFrame).toBeTruthy()
    await previewFrame!.goto(previewFrame!.url())
    await expect(runtime.locator('.presenter-console')).toBeVisible()
    await expect(runtime.locator('.presenter-console__display-status')).toContainText('全屏中', { timeout: 15_000 })

    /** 在控制台重载后向新观众 owner 投递旧 owner 与旧协议的播放命令，检查不会接管新会话。 */
    await reopened.evaluate(() => {
      const key = Object.keys(localStorage).find(item => item.startsWith('web-presentation.presenter.sync.'))
      if (!key) throw new Error('缺少控制台同步消息')
      const stored = JSON.parse(localStorage.getItem(key) ?? '{}') as { message: Record<string, unknown> }
      const base = stored.message
      const channel = new BroadcastChannel(`web-presentation:presenter:${String(base.channelId)}`)
      const common = {
        channelId: base.channelId,
        artifactIdentity: base.artifactIdentity,
        role: 'console',
        revision: Number.MAX_SAFE_INTEGER,
        type: 'playback-command',
        action: 'set-auto-advance',
        autoAdvance: true,
      }
      channel.postMessage({
        ...common,
        protocol: 4,
        sourceId: 'g1-late-old-owner',
        ownerEpoch: 0,
        eventId: 'g1-late-old-owner:1',
        commandId: 'g1-late-old-owner-command',
      })
      channel.postMessage({
        ...common,
        protocol: 3,
        sourceId: 'g1-late-old-protocol',
        ownerEpoch: Number.MAX_SAFE_INTEGER,
        eventId: 'g1-late-old-protocol:1',
        commandId: 'g1-late-old-protocol-command',
      })
      channel.close()
    })
    await page.waitForTimeout(400)
    await expect(runtime.getByTestId('presenter-playback-auto')).toHaveText('手动')
    await runtime.getByRole('region', { name: '观众放映状态' }).getByRole('button', { name: '上一页' }).click()
    await expect(reopened.locator('.smoke-page')).toBeVisible()
  } finally {
    await api.patch(`/api/pages/${secondPage.id}`, { data: { status: 'archived' } }).catch(() => undefined)
  }
})

test('观众窗口独占时间轴播放，控制台保持静态海报', async ({ page, context, visualEditSandbox }) => {
  test.setTimeout(180_000)
  const source = `<template>
  <main ref="root"><h1 class="presenter-motion-title">演讲时间轴</h1></main>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { usePageTimeline } from '@runtime-kit/public/composables/motion/usePageTimeline.v1'
const root = ref<HTMLElement | null>(null)
usePageTimeline({
  root,
  bindings: { title: '.presenter-motion-title' },
  applyPoster: true,
  definition: {
    schemaVersion: 1,
    timelineId: 'presenter-owner',
    poster: { atMs: 4000 },
    tracks: [{ type: 'dom', id: 'title', target: 'title', preset: 'fade', durationMs: 4000 }],
  },
})
</script>
<style scoped>.presenter-motion-title { font-size: 64px; color: #b91c1c; }</style>`
  const api = context.request
  const updateResponse = await api.patch(`/api/pages/${visualEditSandbox.pageId}`, { data: { page_content: source } })
  expect(updateResponse.ok(), await updateResponse.text()).toBeTruthy()
  const artifactResponse = await api.post(`/api/projects/${visualEditSandbox.projectId}/preview-artifacts`, { data: {} })
  expect(artifactResponse.ok(), await artifactResponse.text()).toBeTruthy()
  const artifact = await artifactResponse.json() as { preview_url: string }
  await page.goto(artifact.preview_url)
  const runtime = page.frameLocator('iframe#preview')
  const popupPromise = page.waitForEvent('popup')
  await runtime.locator('.nav-button--presenter').click()
  const display = await popupPromise
  const consoleTitle = runtime.locator('.presenter-console__preview-content .presenter-motion-title').first()
  const displayTitle = display.locator('.presenter-display-screen__content .presenter-motion-title')
  await expect(consoleTitle).toBeVisible()
  await expect(displayTitle).toBeVisible()
  await expect.poll(() => consoleTitle.evaluate(element => getComputedStyle(element).opacity)).toBe('1')
  await display.getByRole('button', { name: '当前窗口全屏' }).click()
  const transport = runtime.getByRole('region', { name: '观众放映状态' })
  await expect(transport.locator('[data-testid="presenter-playback-state"]')).toContainText('放映中')
  await expect.poll(async () => {
    const opacity = Number(await displayTitle.evaluate(element => getComputedStyle(element).opacity))
    return opacity > 0.05 && opacity < 0.9
  }).toBe(true)
  await expect.poll(() => consoleTitle.evaluate(element => getComputedStyle(element).opacity)).toBe('1')
  /** 在观众窗口内经真实 BroadcastChannel 发送控制台命令，避免 Headless Chromium 切焦后撤销全屏。 */
  const sendCommand = async (
    action: 'pause' | 'resume' | 'set-auto-advance',
    revision: number,
    options: { commandId?: string; autoAdvance?: boolean } = {},
  ) => {
    await display.evaluate(({ action: commandAction, revision: commandRevision, commandId, autoAdvance }) => {
      const key = Object.keys(localStorage).find(item => item.startsWith('web-presentation.presenter.sync.'))
      if (!key) throw new Error('缺少控制台同步消息')
      const stored = JSON.parse(localStorage.getItem(key) ?? '{}') as { message: Record<string, unknown> }
      const base = stored.message
      const channel = new BroadcastChannel(`web-presentation:presenter:${String(base.channelId)}`)
      channel.postMessage({
        protocol: 4, channelId: base.channelId, artifactIdentity: base.artifactIdentity,
        sourceId: 'g1-command-probe', role: 'console', ownerEpoch: base.ownerEpoch,
        revision: commandRevision, eventId: `g1-command-${commandRevision}`,
        commandId: commandId ?? `g1-command-${commandRevision}`, type: 'playback-command', action: commandAction,
        ...(autoAdvance === undefined ? {} : { autoAdvance }),
      })
      channel.close()
    }, { action, revision, ...options })
  }
  await sendCommand('pause', 1)
  await expect(transport.locator('[data-testid="presenter-playback-state"]')).toContainText('已暂停')
  const pausedOpacity = await displayTitle.evaluate(element => getComputedStyle(element).opacity)
  await page.waitForTimeout(500)
  expect(await displayTitle.evaluate(element => getComputedStyle(element).opacity)).toBe(pausedOpacity)

  await sendCommand('set-auto-advance', 2, { commandId: 'g1-duplicate-command', autoAdvance: true })
  await expect(transport.locator('[data-testid="presenter-playback-auto"]')).toHaveText('自动')
  await sendCommand('set-auto-advance', 3, { commandId: 'g1-duplicate-command', autoAdvance: false })
  await page.waitForTimeout(500)
  await expect(transport.locator('[data-testid="presenter-playback-auto"]')).toHaveText('自动')

  await sendCommand('resume', 4)
  await expect.poll(() => displayTitle.evaluate(element => getComputedStyle(element).opacity), { timeout: 10000 }).toBe('1')
  await expect.poll(() => consoleTitle.evaluate(element => getComputedStyle(element).opacity)).toBe('1')
})
