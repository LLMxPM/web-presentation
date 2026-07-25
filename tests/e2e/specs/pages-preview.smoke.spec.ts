/**
 * 文件功能：覆盖平台 E2E 冒烟中的页面列表进入、页面详情打开与预览 iframe 可见主链路。
 */
import { expect, test, type Locator, type Page } from '@playwright/test'

import { loginAsAdmin } from '../helpers/auth'
import { openFirstPage, openFirstProject, waitForWorkspaceHome } from '../helpers/navigation'

test('创建后的页面应可进入详情并展示预览 iframe', async ({ page }) => {
  await loginAsAdmin(page)
  await waitForWorkspaceHome(page)
  await openFirstProject(page)
  await openFirstPage(page)
  await expect(page.locator('[data-testid="page-preview-frame"]')).toBeVisible()
})

test('可视化编辑应支持循环项复制、删除并分别保存刷新', async ({ page }) => {
  await loginAsAdmin(page)
  await waitForWorkspaceHome(page)
  await openFirstProject(page)
  await openFirstPage(page)

  await page.getByRole('button', { name: '编辑', exact: true }).click()
  const layerTree = page.getByRole('tree', { name: '页面容器层级' })
  const loopNode = layerTree.getByRole('button', { name: /li.*v-for/ })
  await loopNode.click()

  const instanceSelector = page.getByRole('combobox')
  await expectLoopInstanceCount(page, instanceSelector, 2)
  await page.getByRole('button', { name: '复制此项', exact: true }).click()
  await expect(page.getByText('1 项待保存', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '保存并刷新', exact: true }).click()
  await expect(page.getByText('1 项待保存', { exact: true })).toBeHidden()

  await layerTree.getByRole('button', { name: /li.*v-for/ }).click()
  await expectLoopInstanceCount(page, instanceSelector, 3)
  await instanceSelector.click()
  await page.getByRole('option', { name: 'key: smoke-1-copy（第 2 项）', exact: true }).click()
  await page.getByRole('button', { name: '删除此项', exact: true }).click()
  await expect(page.getByRole('heading', { name: '删除此项', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '确定', exact: true }).click()
  await expect(page.getByText('1 项待保存', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '保存并刷新', exact: true }).click()
  await expect(page.getByText('1 项待保存', { exact: true })).toBeHidden()

  await layerTree.getByRole('button', { name: /li.*v-for/ }).click()
  await instanceSelector.click()
  await expect(page.getByRole('option')).toHaveCount(2)
  await expect(page.getByRole('option', { name: /smoke-1-copy/ })).toHaveCount(0)
})

/** 展开 Reka UI 选择器后，校验当前循环实例数量并关闭浮层。 */
async function expectLoopInstanceCount(page: Page, instanceSelector: Locator, count: number) {
  await instanceSelector.click()
  await expect(page.getByRole('option')).toHaveCount(count)
  await page.keyboard.press('Escape')
}
