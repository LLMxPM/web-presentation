/**
 * 文件功能：覆盖真实项目构建重型链路：在夹具沙箱项目发起构建，等待 Runtime 构建完成并校验产物状态。
 */
import { expect, test } from '../../fixtures/test-data'

interface BuildJob {
  id: number
  status: string
}

test('沙箱项目应完成一次真实构建并展示构建成功', async ({ page, context, visualEditSandbox }) => {
  await page.goto(`/workspaces/${visualEditSandbox.workspaceId}/projects/${visualEditSandbox.projectId}/pages`)
  await expect(page.locator('[data-testid="project-pages-view"]')).toBeVisible()
  await page.locator('[data-testid="project-build-open"]').click()
  await expect(page.locator('[data-testid="project-build-dialog"]')).toBeVisible()
  await page.getByRole('button', { name: '发起构建' }).click()

  // 真实构建经由 Backend 构建队列委托 Runtime 执行，轮询任务状态直至终态。
  const api = context.request
  await expect(async () => {
    const response = await api.get(`/api/projects/${visualEditSandbox.projectId}/build-jobs/latest`)
    expect(response.ok()).toBeTruthy()
    const job = (await response.json()) as BuildJob | null
    expect(job, '构建任务尚未创建').not.toBeNull()
    expect(job!.status, `构建任务 #${job!.id} 当前状态`).toBe('succeeded')
  }).toPass({ timeout: 360_000, intervals: [2_000] })

  // 产物可下载说明构建输出已真实托管。
  const artifact = await api.get(`/api/projects/${visualEditSandbox.projectId}/build-jobs/latest`)
  const latestJob = (await artifact.json()) as BuildJob
  const artifactResponse = await api.get(
    `/api/projects/${visualEditSandbox.projectId}/build-jobs/${latestJob.id}/artifact`,
  )
  expect(artifactResponse.ok()).toBeTruthy()

  // 提交后弹窗会自动关闭；重新打开并刷新，验证用户可见的历史状态与下载入口。
  await page.locator('[data-testid="project-build-open"]').click()
  const buildDialog = page.locator('[data-testid="project-build-dialog"]')
  await expect(buildDialog).toBeVisible()
  await buildDialog.getByRole('button', { name: '刷新最新状态' }).click()
  await expect(buildDialog.getByText('成功', { exact: true })).toBeVisible()
  await expect(buildDialog.getByRole('button', { name: 'ZIP', exact: true })).toBeVisible()
})
