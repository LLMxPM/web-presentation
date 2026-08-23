/**
 * 文件功能：串行覆盖内容助手普通对话与视觉链路，避免共享工作空间的活动会话在并行用例间切换；
 * 会话、运行、工具调用、图片理解与固定 PNG 生成资源落库全部走真实 Backend。
 */
import type { Page } from '@playwright/test'

import { expect, test } from '../../fixtures/base'

import { AGENT_HELLO_CASE, AGENT_PAGE_EXTERNAL_CASE, AGENT_VISUAL_CASE, buildReferenceImage } from '../../fixtures/ai-cases'
import { openAgentPanel, prepareIsolatedAgentPanel, waitForVisualCapability } from '../../helpers/ai-panel'
import { gotoWorkspaceHome, openSmokePage, openSmokeProject } from '../../helpers/navigation'

test('内容助手普通对话应走真实会话链路并返回确定性终态文本', async ({ page }) => {
  await gotoWorkspaceHome(page)
  const panel = await prepareIsolatedAgentPanel(page)

  await panel.locator('textarea').fill(AGENT_HELLO_CASE.input)
  await panel.getByRole('button', { name: /发送/ }).click()

  await expect(panel.getByText(AGENT_HELLO_CASE.finalText).last()).toBeVisible({ timeout: 30_000 })
})

test('页面创建应经过 external job 并直接恢复父 Run', async ({ page }) => {
  await gotoWorkspaceHome(page)
  await openSmokeProject(page)
  await openSmokePage(page)
  const panel = await prepareIsolatedAgentPanel(page)

  await panel.locator('textarea').fill(AGENT_PAGE_EXTERNAL_CASE.input)
  await panel.getByRole('button', { name: /发送/ }).click()

  // 并发运行其它写型夹具时，目标项目可能落在当前焦点之外，从而进入 HITL；
  // 单独运行时则会直接进入 external job，兼容这两种合法路径。
  const confirmation = panel.getByText('允许执行 创建页面 吗？', { exact: true })
  const finalText = panel.getByText(AGENT_PAGE_EXTERNAL_CASE.finalText).last()
  let confirmationRequired = false
  await Promise.any([
    confirmation.waitFor({ state: 'visible', timeout: 15_000 }).then(() => {
      confirmationRequired = true
    }),
    finalText.waitFor({ state: 'visible', timeout: 60_000 }),
  ])
  if (confirmationRequired) {
    await panel.getByRole('button', { name: '提交', exact: true }).click()
  }

  await expect(finalText).toBeVisible({ timeout: 60_000 })
  const toolGroup = panel.locator('[data-testid="tool-call-group"]').last()
  await expect(toolGroup).toBeVisible()
  await expect(panel.getByRole('button', { name: `新增页面：${AGENT_PAGE_EXTERNAL_CASE.pageTitle}` })).toBeVisible()

  await page.reload()
  await page.waitForSelector('[data-testid="page-detail-view"]', { timeout: 15_000 })
  await openAgentPanel(page)
  await expect(panel.getByText(AGENT_PAGE_EXTERNAL_CASE.finalText).last()).toBeVisible({ timeout: 30_000 })
})

test('视觉链路应真实经历理解、生成与保存并可在刷新后恢复', async ({ page }) => {
  await gotoWorkspaceHome(page)
  await openSmokeProject(page)
  await openSmokePage(page)
  const panel = await prepareIsolatedAgentPanel(page)
  await waitForVisualCapability(panel)

  const fileInput = panel.locator('input[type="file"]')
  await fileInput.setInputFiles([
    buildReferenceImage('reference-a.png'),
    buildReferenceImage('reference-b.png'),
  ])
  await expect(page.getByAltText('reference-a.png').first()).toBeVisible()
  await expect(page.getByAltText('reference-b.png').first()).toBeVisible()
  await expect(page.getByText('已添加 2/10 张')).toBeVisible()

  await panel.locator('textarea').fill(AGENT_VISUAL_CASE.input)
  await panel.getByRole('button', { name: /发送/ }).click()

  // deferred 图片任务由后台队列恢复，链路包含真实 waiting_external → running → completed。
  await expectVisualToolResult(panel, { timeout: 60_000 })

  await page.reload()
  await page.waitForSelector('[data-testid="page-detail-view"]', { timeout: 15_000 })
  await openAgentPanel(page)
  await expectVisualToolResult(panel, { timeout: 30_000 })
})

test('内容助手在资源库页面仍应展示视觉能力并允许上传参考图', async ({ page }) => {
  await gotoWorkspaceHome(page)
  await page.locator('[data-testid="workspace-dock-assets"]').click()
  await expect(page.locator('[data-testid="assets-view"]')).toBeVisible()
  const panel = await openAgentPanel(page)
  const visualStatus = panel.locator('[data-testid="visual-status-region"]')
  await expect(visualStatus.getByTitle('analyze_visuals 已配置，可按需分析附件、工作空间图片资源或页面截图')).toBeVisible()
  await expect(visualStatus.getByTitle('generate_image 已配置，可生成或编辑图片并保存到资源库')).toBeVisible()
  await expect(panel.getByLabel('上传图片')).toBeEnabled()
})

/**
 * 只断言用户可见产物：工具分组、图片理解/生成卡片、真实资源名与已保存提示；
 * 不断言事件序列的私有结构（e2e-redesign.md §3.5）。
 */
async function expectVisualToolResult(panel: ReturnType<Page['locator']>, options: { timeout: number }) {
  await expect(panel.getByText(AGENT_VISUAL_CASE.finalExpectation).last()).toBeVisible({ timeout: options.timeout })

  const toolGroup = panel.locator('[data-testid="tool-call-group"]').last()
  await expect(toolGroup).toBeVisible()
  await toolGroup.locator(':scope > summary').click()

  const generationCard = toolGroup.locator('[data-testid="visual-tool-card"]').filter({ hasText: '图片生成' })
  await expect(toolGroup.getByText('图片理解', { exact: true })).toBeVisible()
  await expect(generationCard).toBeVisible()
  await generationCard.locator(':scope > summary').click()
  await expect(generationCard.getByRole('button', {
    name: new RegExp(`预览图片 ${AGENT_VISUAL_CASE.assetNamePrefix}`),
  })).toBeVisible()
  await expect(generationCard.getByRole('button', { name: /已保存到资源库/ })).toBeVisible()
}
