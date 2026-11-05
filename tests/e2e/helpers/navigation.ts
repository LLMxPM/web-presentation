/**
 * 文件功能：封装平台 E2E 常用页面跳转与等待逻辑，减少 spec 中的重复步骤。
 *
 * 工作空间首页按显式 ID 进入：Editor 的 `/` 入口会跳转「最后打开」的工作空间，
 * 而 AI 用例在专属工作空间内活动会改写该排序（新建空间 last_opened_at 为空，
 * PostgreSQL 的 DESC 默认把空值排在最前），按名称解析后才能避免用例间串台。
 */
import { expect, type Page } from '@playwright/test'

/** 全局冒烟工作空间名称，与 backend/app/scripts/test_data.py 的 seed 一致。 */
const SMOKE_WORKSPACE_NAME = 'Smoke Workspace'

/** worker 内缓存的空间 ID：同一 worker 的多个用例无需重复查询列表。 */
let smokeWorkspaceId: number | null = null

/**
 * 解析全局冒烟工作空间 ID；夹具只读引用该空间，不对其做任何写操作。
 */
async function resolveSmokeWorkspaceId(page: Page): Promise<number> {
  if (smokeWorkspaceId !== null) return smokeWorkspaceId

  const response = await page.request.get('/api/workspaces', {
    params: { keyword: SMOKE_WORKSPACE_NAME, page: 1, page_size: 100 },
  })
  if (!response.ok()) {
    throw new Error(`工作空间列表查询失败：HTTP ${response.status()}`)
  }
  const body = (await response.json()) as { items: Array<{ id: number; name: string }> }
  const workspace = body.items.find(item => item.name === SMOKE_WORKSPACE_NAME)
  if (!workspace) {
    throw new Error(`未找到全局冒烟工作空间 ${SMOKE_WORKSPACE_NAME}，请先执行 pnpm run test:e2e:prepare。`)
  }
  smokeWorkspaceId = workspace.id
  return smokeWorkspaceId
}

/**
 * 已登录用例的统一入口：storageState 已携带登录态，直接进入冒烟工作空间首页，不重复登录。
 */
export async function gotoWorkspaceHome(page: Page) {
  await page.goto(`/workspaces/${await resolveSmokeWorkspaceId(page)}/home`)
  await waitForWorkspaceHome(page)
}

export async function waitForWorkspaceHome(page: Page) {
  await expect(page.locator('[data-testid="workspace-project-list"]')).toBeVisible()
}

export async function openSmokeProject(page: Page) {
  const smokeProject = page.getByRole('link', { name: '打开项目：Smoke Project', exact: true })
  await expect(smokeProject).toBeVisible()
  await smokeProject.click()
  await expect(page.locator('[data-testid="project-pages-view"]')).toBeVisible()
}

export async function openSmokePage(page: Page) {
  const smokePage = page.locator('[data-testid="page-card"]').filter({
    has: page.getByRole('button', { name: '复制页面名称：Smoke Page', exact: true }),
  })
  await expect(smokePage).toBeVisible()
  await smokePage.click()
  await expect(page.locator('[data-testid="page-detail-view"]')).toBeVisible()
}
