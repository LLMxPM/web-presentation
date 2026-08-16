/**
 * 文件功能：覆盖可视化编辑真实写入链路；三个写型用例均使用用例级独立夹具
 * （见 fixtures/test-data.ts），不修改全局 Smoke Page，保证单独跑、乱序跑、
 * 并行跑与失败重跑结果一致（e2e-redesign.md §3.1）。
 */
import { test } from '../../fixtures/test-data'
import { expect } from '../../fixtures/base'
import type { Locator, Page } from '@playwright/test'

test('可视化编辑应支持循环项复制、删除并分别保存刷新', async ({ page, visualEditSandbox }) => {
  await page.getByRole('button', { name: '编辑', exact: true }).click()
  await page.getByRole('button', { name: '页面结构（高级）', exact: true }).click()
  const layerTree = page.getByRole('tree', { name: '页面结构' })
  const loopNode = layerTree.getByRole('button', { name: /列表项.*v-for/ })
  await loopNode.click()

  const instanceSelector = page.getByRole('combobox')
  await expectLoopInstanceCount(page, instanceSelector, 2)
  await page.getByRole('button', { name: '复制此项', exact: true }).click()
  await expect(page.getByText('1 项待保存', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText('1 项待保存', { exact: true })).toBeHidden()

  await layerTree.getByRole('button', { name: /列表项.*v-for/ }).click()
  await expectLoopInstanceCount(page, instanceSelector, 3)
  await instanceSelector.click()
  await page.getByRole('option', { name: 'key: smoke-1-copy（第 2 项）', exact: true }).click()
  await page.getByRole('button', { name: '删除此项', exact: true }).click()
  await expect(page.getByRole('heading', { name: '删除此项', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '确定', exact: true }).click()
  await expect(page.getByText('1 项待保存', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText('1 项待保存', { exact: true })).toBeHidden()

  await layerTree.getByRole('button', { name: /列表项.*v-for/ }).click()
  await instanceSelector.click()
  await expect(page.getByRole('option')).toHaveCount(2)
  await expect(page.getByRole('option', { name: /smoke-1-copy/ })).toHaveCount(0)
})

test('可视化编辑应从画布选择标题并修改常用文字样式', async ({ page, visualEditSandbox }) => {
  await page.getByRole('button', { name: '编辑', exact: true }).click()
  await expect(page.getByText('点击画布中的文字、区块或组件进行编辑', { exact: true })).toBeVisible()

  const visualFrame = page.frameLocator('iframe[title$="可视化编辑画布"]')
  await visualFrame.getByRole('heading', { name: visualEditSandbox.pageTitle, exact: true }).click()
  // 检查器标题超过 18 字符会被截断，只断言稳定的节点类型与页面前缀。
  await expect(page.getByRole('heading', { name: /^标题：VE 画布页/ })).toBeVisible()

  await page.getByRole('tab', { name: '样式', exact: true }).click()
  const weightSelect = page.getByRole('combobox', { name: '字重' })
  await weightSelect.click()
  await page.getByRole('option', { name: '半粗字重', exact: true }).click()
  await expect(page.getByText(/特粗字重\s*→\s*半粗字重/)).toBeVisible()
  const saveButton = page.getByRole('button', { name: '保存', exact: true })
  await expect(saveButton).not.toBeDisabled()
  await saveButton.click()
  await expect(saveButton).toBeDisabled()
  await expect(visualFrame.getByRole('heading', { name: visualEditSandbox.pageTitle, exact: true })).toHaveClass(/font-semibold/)
})

test('AssetImage 专用检查器应替换资源、填充和图片框圆角并保存', async ({ page, visualEditSandbox }) => {
  await page.getByRole('button', { name: '编辑', exact: true }).click()
  const visualFrame = page.frameLocator('iframe[title$="可视化编辑画布"]')
  const image = visualFrame.getByRole('img', { name: 'Smoke illustration', exact: true })
  const originalSource = await image.getAttribute('src')
  await image.click()
  await expect(page.getByRole('heading', { name: /图片：Smoke illustration/ })).toBeVisible()

  await page.getByRole('button', { name: '选择图片资源', exact: true }).click()
  const pickerDialog = page.getByRole('dialog', { name: '选择图片资源' })
  const replacementCard = pickerDialog.getByRole('button', { name: /smoke-image-b/ })
  const replacementSource = await replacementCard.getByRole('img', { name: 'smoke-image-b' }).getAttribute('src')
  await replacementCard.click()
  await pickerDialog.getByRole('button', { name: '确认选择', exact: true }).click()
  await expect(pickerDialog).not.toBeVisible()

  const fitSelect = page.getByRole('combobox', { name: '框内填充' })
  await fitSelect.click()
  await page.getByRole('option', { name: '原始尺寸', exact: true }).click()
  await page.getByText(/\d+ 项待保存/).waitFor({ state: 'visible', timeout: 5000 })
  await fitSelect.click()
  await page.getByRole('option', { name: '填满并裁切', exact: true }).click()

  const radiusSelect = page.getByRole('combobox', { name: '圆角' })
  await radiusSelect.click()
  await page.getByRole('option', { name: '轻微圆角', exact: true }).click()
  await radiusSelect.click()
  await page.getByRole('option', { name: '超大圆角', exact: true }).click()

  const saveButton = page.getByRole('button', { name: '保存', exact: true })
  await expect(saveButton).not.toBeDisabled()
  await saveButton.click()
  await expect(saveButton).toBeDisabled()

  await expect(image).toHaveCSS('object-fit', 'cover')
  await expect(image.locator('xpath=ancestor::figure[1]')).toHaveClass(/rounded-2xl/)
  await expect(image).toHaveAttribute('src', replacementSource!)
  expect(replacementSource).not.toBe(originalSource)
})

/** 展开 Reka UI 选择器后，校验当前循环实例数量并关闭浮层。 */
async function expectLoopInstanceCount(page: Page, instanceSelector: Locator, count: number) {
  await instanceSelector.click()
  await expect(page.getByRole('option')).toHaveCount(count)
  await page.keyboard.press('Escape')
}
