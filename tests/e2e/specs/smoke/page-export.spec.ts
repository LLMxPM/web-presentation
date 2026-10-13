/**
 * 文件功能：覆盖 Runtime 导出弹窗到真实 .pptx 下载产物的链路，确保可编辑 PPTX 导出不止于按钮可点。
 *
 * 断言口径与 page-screenshot.spec.ts 对齐：校验真实产物的容器魔数、关键 OOXML 条目与体积下限，
 * 不以「按钮可见」或占位文案代替产物断言。完整 OOXML 结构由
 * runtime/src/core/services/pptx/PPTXDomConverterTable.integration.test.ts 在单测层覆盖。
 */
import { readFileSync } from 'node:fs'

import { expect, test } from '../../fixtures/base'

import { gotoWorkspaceHome, openSmokePage, openSmokeProject } from '../../helpers/navigation'

/** OOXML 演示文稿必需的幻灯片条目；缺失说明产出的不是可编辑 PPTX。 */
const SLIDE_ENTRY = 'ppt/slides/slide1.xml'

/** ZIP 本地文件头魔数 PK\x03\x04。 */
const ZIP_LOCAL_HEADER = Buffer.from([0x50, 0x4b, 0x03, 0x04])

/** 单页 PPTX 的体积下限；低于该值说明只写出了空壳包。 */
const MIN_PPTX_BYTES = 4 * 1024

test('页面导出应产出可下载的真实 PPTX 产物', async ({ page }, testInfo) => {
  test.setTimeout(180_000)
  await gotoWorkspaceHome(page)
  await openSmokeProject(page)
  await openSmokePage(page)

  const previewFrame = page.frameLocator('[data-testid="page-preview-frame"]')

  const exportButton = previewFrame.locator('.nav-button--export')
  await expect(exportButton).toBeVisible()
  await exportButton.click()

  const dialog = previewFrame.locator('[role="dialog"][aria-labelledby="export-dialog-title"]')
  await expect(dialog).toBeVisible()
  // 默认即为 HTML转PPTX + 当前页面，不再切换选项，避免把导出断言耦合到表单交互。
  await expect(dialog.locator('input[value="pptx-editable"]')).toBeChecked()
  await expect(dialog.locator('input[value="current"]')).toBeChecked()

  const downloadPromise = page.waitForEvent('download')
  await dialog.getByRole('button', { name: '开始导出' }).click()
  const download = await downloadPromise

  expect(download.suggestedFilename()).toMatch(/\.pptx$/)
  const artifactPath = await download.path()
  expect(artifactPath, '下载未落地为可读文件').toBeTruthy()

  const pptx = readFileSync(artifactPath as string)
  expect(pptx.byteLength, '产物体积过小，疑似空壳包').toBeGreaterThan(MIN_PPTX_BYTES)
  expect(pptx.subarray(0, 4), '产物不是 ZIP 容器').toEqual(ZIP_LOCAL_HEADER)
  expect(pptx.includes(Buffer.from(SLIDE_ENTRY)), `产物缺少 ${SLIDE_ENTRY} 条目`).toBe(true)

  await testInfo.attach('exported.pptx', {
    body: pptx,
    contentType: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  })
})
