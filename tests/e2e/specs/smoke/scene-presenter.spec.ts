/**
 * 文件功能：用真实双窗口 Chromium 验证演讲控制台与唯一观众窗口的 v5 联动。
 * 协议只有 request-state、有限 intent 与观众原子 state；旧协议、旧修订与旧 owner 一律被丢弃。
 */
import type { Page } from '@playwright/test'
import { expect, test } from '../../fixtures/test-data'
import { buildScenePage } from '../../helpers/scene-page-source'

/** 在观众窗口内监听并返回控制台发来的第一条真实 v5 消息，作为注入基底。 */
async function installEnvelopeProbe(display: Page): Promise<void> {
  await display.evaluate(() => {
    const target = window as unknown as { __presenterEnvelope?: Record<string, unknown> }
    const channel = new BroadcastChannel(`web-presentation:presenter:v5:${new URLSearchParams(location.search).get('channel') ?? ''}`)
    channel.onmessage = event => {
      const message = event.data as Record<string, unknown>
      if (message?.protocol === 5 && !target.__presenterEnvelope) target.__presenterEnvelope = message
    }
  })
}

/** 读取已捕获的真实信封；控制台尚未发送任何意图时失败，避免用猜测身份伪造消息。 */
async function readEnvelope(display: Page): Promise<Record<string, unknown>> {
  return await display.evaluate(() => {
    const envelope = (window as unknown as { __presenterEnvelope?: Record<string, unknown> }).__presenterEnvelope
    if (!envelope) throw new Error('没有捕获到控制台发来的 v5 消息')
    return envelope
  })
}

/** 在观众窗口内按真实频道投递伪造消息；只验证接收端丢弃，不引入第二套传输。 */
async function postForged(display: Page, messages: Array<Record<string, unknown>>): Promise<void> {
  await display.evaluate(payload => {
    const channel = new BroadcastChannel(`web-presentation:presenter:v5:${String(payload[0].channelId)}`)
    for (const message of payload) channel.postMessage(message)
    channel.close()
  }, messages)
}

test('演讲模式复用观众窗口并按意图同步翻页', async ({ page, context, visualEditSandbox }) => {
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
    await page.goto((await artifactResponse.json()).preview_url as string)
    const runtime = page.frameLocator('iframe#preview')
    await expect(runtime.locator('.nav-button--presenter')).toBeVisible()
    const popupPromise = page.waitForEvent('popup')
    await runtime.locator('.nav-button--presenter').click()
    const display = await popupPromise
    await expect(runtime.locator('.presenter-console')).toBeVisible()
    await expect(display.locator('.presenter-display-screen')).toBeVisible()
    // 控制台小窗收紧为缩略图策略，观众窗口才是唯一放映画布。
    await expect(runtime.locator('.presenter-console')).toHaveAttribute('data-runtime-execution', 'thumbnail')
    await expect(display.locator('.presenter-display-screen')).toHaveAttribute('data-runtime-execution', 'presentation')
    await installEnvelopeProbe(display)

    await display.getByRole('button', { name: '当前窗口全屏' }).click()
    await expect(runtime.locator('.presenter-console__display-status')).toContainText('全屏中')
    const panel = runtime.locator('.presenter-playback-panel')
    await expect(panel.locator('[data-testid="presenter-playback-state"]')).toContainText('未开始')
    await panel.locator('[data-testid="presenter-playback-primary"]').click()
    await expect(panel.locator('[data-testid="presenter-playback-state"]')).toContainText('放映中')
    await panel.getByRole('button', { name: '下一页' }).click()
    await expect(display.locator('.presenter-e2e-second')).toBeVisible()
    await expect(panel.locator('.presenter-playback-panel__page')).toHaveText('2 / 2')

    // 控制台先发意图、收到观众事实后才更新页码；旧协议与旧修订消息不得改变当前页。
    const envelope = await readEnvelope(display)
    await postForged(display, [
      { ...envelope, protocol: 3, sourceId: 'c3-old-protocol-3', revision: Number.MAX_SAFE_INTEGER },
      { ...envelope, protocol: 4, sourceId: 'c3-old-protocol-4', revision: Number.MAX_SAFE_INTEGER },
      { ...envelope, action: 'navigate', page: '/home', revision: Math.max(1, Number(envelope.revision) - 1) },
    ])
    await page.waitForTimeout(400)
    await expect(display.locator('.presenter-e2e-second')).toBeVisible()
    await expect(panel.locator('.presenter-playback-panel__page')).toHaveText('2 / 2')

    const before = context.pages().length
    await runtime.getByRole('button', { name: '观众窗口', exact: true }).click()
    await expect(display.locator('.presenter-e2e-second')).toBeVisible()
    expect(context.pages().length).toBe(before)

    await display.close()
    expect(context.pages().length).toBe(before - 1)
    const reopenedPromise = page.waitForEvent('popup')
    await runtime.getByRole('button', { name: '观众窗口', exact: true }).click()
    const reopened = await reopenedPromise
    await expect(reopened.locator('.presenter-display-screen')).toBeVisible()
    expect(context.pages().length).toBe(before)
    await reopened.getByRole('button', { name: '当前窗口全屏' }).click()
    await expect(runtime.locator('.presenter-console__display-status')).toContainText('全屏中', { timeout: 15_000 })

    // 新观众窗口接管调度；控制台按当前事实重新对齐页码。
    await expect(panel.locator('[data-testid="presenter-playback-state"]')).not.toContainText('观众窗口已关闭')
    await panel.getByRole('button', { name: '上一页' }).click()
    await expect(reopened.locator('.smoke-page')).toBeVisible()
    await expect(panel.locator('.presenter-playback-panel__page')).toHaveText('1 / 2')

    // 保持/释放只抑制自动翻页，不暂停 Scene，也不改写项目配置。
    await panel.locator('[data-testid="presenter-playback-hold"]').click()
    await expect(panel.locator('[data-testid="presenter-playback-state"]')).toContainText('保持当前页')
    await panel.locator('[data-testid="presenter-playback-hold"]').click()
    await expect(panel.locator('[data-testid="presenter-playback-hold"]')).toHaveText('保持当前页')
  } finally {
    await api.patch(`/api/pages/${secondPage.id}`, { data: { status: 'archived' } }).catch(() => undefined)
  }
})

test('观众窗口独占 Scene 播放，控制台保持静态默认态', async ({ page, context, visualEditSandbox }) => {
  test.setTimeout(180_000)
  const api = context.request
  const update = await api.patch(`/api/pages/${visualEditSandbox.pageId}`, { data: { page_content: buildScenePage() } })
  expect(update.ok(), await update.text()).toBeTruthy()
  const artifactResponse = await api.post(`/api/projects/${visualEditSandbox.projectId}/preview-artifacts`, { data: {} })
  expect(artifactResponse.ok(), await artifactResponse.text()).toBeTruthy()
  await page.goto((await artifactResponse.json()).preview_url as string)
  const runtime = page.frameLocator('iframe#preview')
  const popupPromise = page.waitForEvent('popup')
  await runtime.locator('.nav-button--presenter').click()
  const display = await popupPromise
  const consoleTitle = runtime.locator('.presenter-console__preview-content .scene-e2e-title').first()
  const consoleCounter = runtime.locator('.presenter-console__preview-content .scene-e2e-counter').first()
  const displayTitle = display.locator('.presenter-display-screen__content .scene-e2e-title')
  const displayCounter = display.locator('.presenter-display-screen__content .scene-e2e-counter')
  await expect(consoleTitle).toBeVisible()
  await expect(displayTitle).toBeVisible()
  // 未开始放映时两侧都是完整可读的静态默认态。
  await expect.poll(() => consoleTitle.evaluate(element => getComputedStyle(element).opacity)).toBe('1')
  await expect(consoleCounter).toHaveText('0')
  await expect(displayCounter).toHaveText('0')

  await display.getByRole('button', { name: '当前窗口全屏' }).click()
  const panel = runtime.locator('.presenter-playback-panel')
  await panel.locator('[data-testid="presenter-playback-primary"]').click()
  await expect(panel.locator('[data-testid="presenter-playback-state"]')).toContainText('放映中')
  // 只有观众窗口执行 Scene；控制台缩略图不启动任务，也不构成第二个发声或调度所有者。
  await expect(displayCounter).toHaveText('100', { timeout: 20_000 })
  await expect(consoleCounter).toHaveText('0')
  await expect.poll(() => consoleTitle.evaluate(element => getComputedStyle(element).opacity)).toBe('1')
  await expect(display.locator('[data-testid="playback-hold-toggle"]')).toBeVisible()
})
