/**
 * 文件功能：验证账号 AI 设置中模型推理策略的创建、编辑、重开与清理主链路。
 */
import { expect, test } from '../../fixtures/base'

test('模型配置应保存三态推理策略并固定展示四档强度', async ({ page }) => {
  const modelName = `E2E 推理策略 ${Date.now()}`

  await page.goto('/account/ai-settings?section=models')
  await expect(page.getByRole('heading', { name: '模型管理' })).toBeVisible()
  await page.getByRole('button', { name: '新建模型' }).click()

  await expect(page.getByRole('radio', { name: '跟随模型' })).toBeChecked()
  await expect(page.getByRole('spinbutton', { name: '平台可用输入窗口（K）' })).toHaveValue('200')
  await expect(page.getByText('232,768', { exact: true })).toBeVisible()
  await expect(page.getByText('167,232', { exact: true })).toBeVisible()
  await expect(page.getByText('32,768', { exact: true })).toBeVisible()
  await expect(page.getByText('16,384', { exact: true })).toBeVisible()
  await page.getByRole('textbox', { name: '模型名称', exact: true }).fill(modelName)
  await page.getByRole('textbox', { name: '模型 ID', exact: true }).fill('gpt-5.6')
  await page.getByRole('radio', { name: '指定强度' }).click()
  for (const level of ['快速', '均衡', '深入', '极致']) {
    await expect(page.getByRole('radio', { name: level })).toBeVisible()
  }
  await page.getByRole('radio', { name: '极致' }).click()
  await expect(page.getByText('极致模式可能显著增加延迟和成本。最终生效：max。')).toBeVisible()
  await page.getByRole('button', { name: '创建模型' }).click()

  await expect(page.getByRole('heading', { name: '查看模型' })).toBeVisible()
  await expect(page.getByText('指定强度 · max')).toBeVisible()
  await expect(page.getByText('最终生效：max。')).toBeVisible()

  await page.getByRole('button', { name: '编辑', exact: true }).click()
  await page.getByRole('radio', { name: '跟随模型' }).click()
  await page.getByRole('button', { name: '保存模型' }).click()
  await expect(page.getByRole('heading', { name: '查看模型' })).toBeVisible()
  await expect(page.getByText('跟随模型')).toBeVisible()

  await page.getByRole('button', { name: '关闭模型配置' }).click()
  const modelRow = page.getByRole('row', { name: new RegExp(modelName) })
  await modelRow.getByRole('button', { name: '查看' }).click()
  await expect(page.getByRole('heading', { name: '查看模型' })).toBeVisible()
  await expect(page.getByText('跟随模型默认。')).toBeVisible()

  await page.getByRole('button', { name: '删除', exact: true }).click()
  await page.getByRole('dialog', { name: '删除模型' }).getByRole('button', { name: '确定' }).click()
  await expect(page.getByRole('row', { name: new RegExp(modelName) })).toHaveCount(0)
})
