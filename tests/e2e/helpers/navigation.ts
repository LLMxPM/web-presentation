/**
 * 文件功能：封装平台 E2E 常用页面跳转与等待逻辑，减少 smoke spec 中的重复步骤。
 */
import { expect, type Page } from '@playwright/test'

export async function waitForWorkspaceHome(page: Page) {
  await expect(page.locator('[data-testid="workspace-project-list"]')).toBeVisible()
}

export async function openFirstProject(page: Page) {
  const firstProject = page.locator('[data-testid="project-card"]').first()
  await expect(firstProject).toBeVisible()
  await firstProject.click()
  await expect(page.locator('[data-testid="project-pages-view"]')).toBeVisible()
}

export async function openFirstPage(page: Page) {
  const firstPage = page.locator('[data-testid="page-card"]').first()
  await expect(firstPage).toBeVisible()
  await firstPage.click()
  await expect(page.locator('[data-testid="page-detail-view"]')).toBeVisible()
}
