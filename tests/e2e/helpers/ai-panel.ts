/**
 * 文件功能：封装 AI 用例共用的智能体面板操作：打开面板、新建会话隔离历史、显式选择 mock 模型。
 *
 * 依据 e2e-redesign.md §3.3/§3.5：AI 用例必须走真实会话链路且保持确定性。
 * 同一工作空间的会话与模型选择会被并行用例共享，因此每个用例必须：
 * 1. 点击「新会话」避免复用其它用例的会话历史；
 * 2. 显式选择 e2e-mock-agent 模型，不依赖面板默认模型（默认值会落到最近创建的聊天配置）。
 */
import { expect, type Locator, type Page } from '@playwright/test'

import { AGENT_MOCK_CONFIG_NAME } from '../fixtures/ai-cases'

/** 打开智能体侧边栏；已打开时直接返回面板定位器。 */
export async function openAgentPanel(page: Page): Promise<Locator> {
  const panel = page.locator('[data-testid="agent-sidebar-panel"]')
  if (!await panel.isVisible()) {
    await page.locator('[data-testid="agent-floating-trigger"]').click()
    await expect(panel).toBeVisible()
  }
  return panel
}

/**
 * 为当前用例准备隔离的面板状态：新建会话草稿并显式选择内容助手 mock 模型。
 * 返回选中后的面板定位器，供后续输入与断言使用。
 */
export async function prepareIsolatedAgentPanel(page: Page): Promise<Locator> {
  const panel = await openAgentPanel(page)

  // 新会话按钮在已有会话时才可见；新建后进入草稿态，避免复用其它用例会话。
  const newSessionButton = panel.getByRole('button', { name: '新会话', exact: true })
  if (await newSessionButton.isVisible().catch(() => false)) {
    await newSessionButton.click()
  }

  await selectAgentMockModel(page, panel)
  return panel
}

/**
 * 等待视觉能力状态就绪（看图/生成图片均可用）。
 * agents 配置接口未返回前上传会被面板静默丢弃，视觉用例上传前必须先等待该状态。
 */
export async function waitForVisualCapability(panel: Locator): Promise<void> {
  const visualStatus = panel.locator('[data-testid="visual-status-region"]')
  await expect(visualStatus.getByTitle(/^analyze_visuals 已配置/)).toBeVisible({ timeout: 15_000 })
  await expect(visualStatus.getByTitle(/^generate_image 已配置/)).toBeVisible({ timeout: 15_000 })
}

/** 通过模型下拉菜单显式选择 e2e-mock-agent 配置，并校验触发按钮已回显。 */
async function selectAgentMockModel(page: Page, panel: Locator): Promise<void> {
  const modelTrigger = panel.locator('button[title^="下次运行模型"], button[title^="新会话模型"]')
  await expect(modelTrigger).toBeEnabled()
  if (await modelTrigger.getByText(AGENT_MOCK_CONFIG_NAME).isVisible().catch(() => false)) {
    return
  }
  await modelTrigger.click()
  await page.getByRole('menuitem', { name: AGENT_MOCK_CONFIG_NAME }).click()
  await expect(modelTrigger).toHaveAttribute('title', new RegExp(AGENT_MOCK_CONFIG_NAME))
}
