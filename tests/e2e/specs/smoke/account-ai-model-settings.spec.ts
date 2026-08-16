/**
 * 文件功能：验证账号 AI 设置中聊天模型的创建、编辑、重开与清理主链路。
 */
import { expect, test } from '../../fixtures/base'

test('聊天模型配置应支持创建、编辑、重开与清理', async ({ page }) => {
  const modelName = `E2E 聊天模型 ${Date.now()}`
  const updatedModelName = `${modelName} 已编辑`

  await page.goto('/account/ai-settings?section=chat')
  await expect(page.getByRole('heading', { name: '聊天模型' })).toBeVisible()
  await page.getByRole('button', { name: '新建模型' }).click()

  const createDialog = page.getByRole('dialog', { name: '新建模型' })
  await expect(createDialog).toBeVisible()
  await createDialog.getByRole('textbox', { name: '模型名称', exact: true }).fill(modelName)
  // 等待异步供应商配置落定；切换供应商会重置模型 ID，不能与模型选择并行操作。
  await expect(createDialog.getByRole('combobox', { name: 'OpenAI Mock 凭证', exact: true })).toBeVisible()
  await createDialog.getByPlaceholder('选择目录模型或手工输入模型 ID').click()
  await page.getByRole('option', { name: '手工输入未收录模型 ID' }).click()
  const customModelId = createDialog.getByRole('textbox', { name: '自定义模型 ID', exact: true })
  await customModelId.fill('gpt-5.6')
  await expect(customModelId).toHaveValue('gpt-5.6')
  await expect(createDialog.getByRole('heading', { name: '模型能力' })).toBeVisible()
  const createButton = createDialog.getByRole('button', { name: '创建模型' })
  await expect(createButton).toBeEnabled()
  await createButton.click()

  let modelDialog = page.getByRole('dialog', { name: modelName })
  await expect(modelDialog).toBeVisible()
  await expect(modelDialog.getByText('平台可用输入窗口')).toBeVisible()
  await expect(modelDialog.getByText('发起会话时按模型能力选择')).toBeVisible()

  await modelDialog.getByRole('button', { name: '编辑', exact: true }).click()
  const editDialog = page.getByRole('dialog', { name: '编辑模型' })
  await expect(editDialog).toBeVisible()
  await editDialog.getByRole('textbox', { name: '模型名称', exact: true }).fill(updatedModelName)
  await editDialog.getByRole('button', { name: '保存模型' }).click()

  modelDialog = page.getByRole('dialog', { name: updatedModelName })
  await expect(modelDialog).toBeVisible()
  await expect(modelDialog.getByRole('heading', { name: updatedModelName })).toBeVisible()

  await modelDialog.getByRole('button', { name: '关闭', exact: true }).click()
  const modelRow = page.getByRole('row', { name: new RegExp(updatedModelName) })
  await modelRow.getByRole('button', { name: '查看' }).click()
  modelDialog = page.getByRole('dialog', { name: updatedModelName })
  await expect(modelDialog).toBeVisible()
  await expect(modelDialog.getByText('聊天 / 图片理解模型')).toBeVisible()

  await modelDialog.getByRole('button', { name: '删除', exact: true }).click()
  await page.getByRole('dialog', { name: '删除模型' }).getByRole('button', { name: '确定' }).click()
  await expect(page.getByRole('row', { name: new RegExp(updatedModelName) })).toHaveCount(0)
})
