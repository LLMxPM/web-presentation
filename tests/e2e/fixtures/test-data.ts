/**
 * 文件功能：为写型 E2E 用例提供用例级独立项目/页面夹具，通过真实 Backend API 创建并在 teardown 最佳努力归档。
 *
 * 依据 docs/developer/testing/e2e-redesign.md §3.1：写型可视化编辑用例不得修改全局 Smoke 数据，
 * 每个用例创建专属项目/页面（名称包含 workerIndex + UUID），teardown 归档失败仅记录附件，
 * 不覆盖原始测试失败。不同 worker/project 不执行全局残留扫描，避免并行归档彼此的活动项目。
 */
import { randomUUID } from 'node:crypto'

import type { APIRequestContext, TestInfo } from '@playwright/test'

import { expect, test as base } from './base'

/** 写型用例专属实体命名空间前缀，供 setup 残留清理与 teardown 归档识别。 */
export const VISUAL_EDIT_NAMESPACE = 'E2E-VisualEdit'

/** 全局 smoke 工作空间名称：夹具只读引用，不对其做任何写操作。 */
const SMOKE_WORKSPACE_NAME = 'Smoke Workspace'

export interface VisualEditSandbox {
  workspaceId: number
  projectId: number
  pageId: number
  pageTitle: string
  pageUrl: string
}

interface PagedItems<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

interface NamedEntity {
  id: number
  name: string
  status: string
}

/**
 * 构造夹具页面源码：与 seed 冒烟页面同构（标题、AssetImage、v-for 列表），
 * 仅标题随用例唯一化，保证可视化编辑断言（字重、圆角、循环项）具备确定基线。
 */
function buildVisualEditPageContent(headingTitle: string): string {
  return `<template>
  <main class="smoke-page">
    <h1 class="text-4xl font-black text-center leading-tight text-slate-900">${headingTitle}</h1>
    <p>platform smoke preview</p>
    <AssetImage
      name="smoke-image-a"
      alt="Smoke illustration"
      fit="contain"
      position="center"
      class="w-48 h-32 p-2 bg-white border rounded-lg"
    />
    <ul>
      <li v-for="item in items" :key="item.id">{{ item.label }}</li>
    </ul>
  </main>
</template>

<script setup lang="ts">
import AssetImage from '@runtime-kit/public/components/assets/AssetImage.v1.vue'

const items = [
  { id: 'smoke-1', label: 'first item' },
  { id: 'smoke-2', label: 'second item' },
]
</script>

<style scoped>
.smoke-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: #f8fafc;
  color: #0f172a;
}
</style>
`
}

/** 只读解析全局 Smoke 工作空间 ID，夹具项目挂载其下以复用已播种的图片资源。 */
async function resolveSmokeWorkspaceId(api: APIRequestContext): Promise<number> {
  const response = await api.get('/api/workspaces', {
    params: { keyword: SMOKE_WORKSPACE_NAME, page: 1, page_size: 100 },
  })
  if (!response.ok()) {
    throw new Error(`工作空间列表查询失败：HTTP ${response.status()}`)
  }
  const body = (await response.json()) as PagedItems<NamedEntity>
  const workspace = body.items.find(item => item.name === SMOKE_WORKSPACE_NAME)
  if (!workspace) {
    throw new Error(`未找到全局冒烟工作空间 ${SMOKE_WORKSPACE_NAME}，请先执行 pnpm run test:e2e:prepare。`)
  }
  return workspace.id
}

/** teardown 最佳努力归档本用例创建的项目与页面；失败仅追加附件，不覆盖原始失败。 */
async function bestEffortArchive(
  api: APIRequestContext,
  created: { projectId?: number; pageId?: number },
  testInfo: TestInfo,
): Promise<void> {
  const failures: string[] = []
  if (created.pageId !== undefined) {
    const response = await api.patch(`/api/pages/${created.pageId}`, { data: { status: 'archived' } }).catch(error => error)
    if (response instanceof Error || !response.ok()) {
      failures.push(`页面 ${created.pageId} 归档失败：${response instanceof Error ? response.message : `HTTP ${response.status()}`}`)
    }
  }
  if (created.projectId !== undefined) {
    const response = await api.patch(`/api/projects/${created.projectId}`, { data: { status: 'archived' } }).catch(error => error)
    if (response instanceof Error || !response.ok()) {
      failures.push(`项目 ${created.projectId} 归档失败：${response instanceof Error ? response.message : `HTTP ${response.status()}`}`)
    }
  }
  if (failures.length) {
    await testInfo.attach('visual-edit-sandbox-teardown-issues', {
      contentType: 'text/plain',
      body: failures.join('\n'),
    })
  }
}

/** 扩展 Playwright test：提供写型可视化编辑用例的隔离项目/页面沙箱。 */
export const test = base.extend<{ visualEditSandbox: VisualEditSandbox }>({
  visualEditSandbox: async ({ page, context }, use, testInfo) => {
    const api = context.request
    const created: { projectId?: number; pageId?: number } = {}
    try {
      // 登录态由 globalSetup 生成的 storageState 提供，夹具不再重复登录。
      const workspaceId = await resolveSmokeWorkspaceId(api)

      // 后缀取 workerIndex + UUID 前 8 位：保证并行唯一性，同时控制标题长度避免界面大量截断。
      const suffix = `w${testInfo.workerIndex}-${randomUUID().slice(0, 8)}`
      const projectResponse = await api.post('/api/projects', {
        data: {
          workspace_id: workspaceId,
          name: `${VISUAL_EDIT_NAMESPACE}-${suffix}`,
          description: 'E2E 写型可视化编辑用例专属项目。',
        },
      })
      if (!projectResponse.ok()) {
        throw new Error(`夹具项目创建失败：HTTP ${projectResponse.status()} ${await projectResponse.text()}`)
      }
      const project = (await projectResponse.json()) as NamedEntity
      created.projectId = project.id

      const pageTitle = `VE 画布页 ${suffix}`
      const pageResponse = await api.post('/api/pages', {
        data: {
          workspace_id: workspaceId,
          project_id: project.id,
          title: pageTitle,
          file_type: 'vue',
          summary: 'E2E 写型可视化编辑用例专属页面。',
          page_content: buildVisualEditPageContent(pageTitle),
        },
      })
      if (!pageResponse.ok()) {
        throw new Error(`夹具页面创建失败：HTTP ${pageResponse.status()} ${await pageResponse.text()}`)
      }
      const createdPage = (await pageResponse.json()) as NamedEntity
      created.pageId = createdPage.id

      // 构建与整项目预览要求至少存在一个页面路由；沙箱在创建后立即建立唯一首页路由。
      const routeResponse = await api.put(`/api/projects/${project.id}/routes`, {
        data: {
          routes: [{
            route_type: 'page',
            route: 'home',
            order: 0,
            hidden: false,
            page_id: createdPage.id,
          }],
        },
      })
      if (!routeResponse.ok()) {
        throw new Error(`夹具项目路由创建失败：HTTP ${routeResponse.status()} ${await routeResponse.text()}`)
      }

      const sandbox: VisualEditSandbox = {
        workspaceId,
        projectId: project.id,
        pageId: createdPage.id,
        pageTitle,
        pageUrl: `/workspaces/${workspaceId}/projects/${project.id}/pages/${createdPage.id}`,
      }
      await page.goto(sandbox.pageUrl)
      await expect(page.locator('[data-testid="page-detail-view"]')).toBeVisible()
      await use(sandbox)
    } finally {
      await bestEffortArchive(api, created, testInfo)
    }
  },
})

export { expect } from './base'
