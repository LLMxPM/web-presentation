/**
 * 文件功能：覆盖平台 E2E 冒烟中的页面列表进入、页面详情打开与预览 iframe 可见主链路。
 */
import { expect, test } from '@playwright/test'

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

  const instanceSelector = page.getByLabel('循环实例')
  await expect(instanceSelector.locator('option')).toHaveCount(2)
  await page.getByRole('button', { name: '复制此项', exact: true }).click()
  await expect(page.getByText('1 项待保存', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '保存并刷新', exact: true }).click()
  await expect(page.getByText('1 项待保存', { exact: true })).toBeHidden()

  await layerTree.getByRole('button', { name: /li.*v-for/ }).click()
  await expect(instanceSelector.locator('option')).toHaveCount(3)
  await instanceSelector.selectOption({ label: 'key: smoke-1-copy（第 2 项）' })
  await page.getByRole('button', { name: '删除此项', exact: true }).click()
  await expect(page.getByRole('heading', { name: '删除此项', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '确定', exact: true }).click()
  await expect(page.getByText('1 项待保存', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '保存并刷新', exact: true }).click()
  await expect(page.getByText('1 项待保存', { exact: true })).toBeHidden()

  await layerTree.getByRole('button', { name: /li.*v-for/ }).click()
  await expect(instanceSelector.locator('option')).toHaveCount(2)
  await expect(instanceSelector.locator('option', { hasText: 'smoke-1-copy' })).toHaveCount(0)
})
