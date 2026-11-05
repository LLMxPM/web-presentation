/**
 * 文件功能：为内容助手 E2E 用例创建专属工作空间、项目与页面，并在用例结束后按序归档。
 *
 * 内容助手是工作空间级智能体：会话、模型绑定与在途 Run 会被同一工作空间内的所有页面看到，
 * 与其它 project 共用 Smoke Workspace 时，并发 AI Run 会出现在别的被测页面侧栏里。
 * 因此 AI 用例自带独立空间，页面写入也落在该空间的专属项目内。
 */
import { randomUUID } from 'node:crypto'

import type { APIRequestContext, TestInfo } from '@playwright/test'

import { test as base, expect } from './base'

/** AI 用例专属工作空间命名前缀，供残留识别。 */
export const AGENT_WORKSPACE_NAMESPACE = 'E2E-AgentWorkspace'

/**
 * mock 页面场景按项目名筛选目标项目（backend/app/ai/testing/scenarios.py 的 PAGE_EXTERNAL_SCENARIO_PROJECT_NAME）。
 * list_entities 只在本会话的工作空间内检索，因此专属空间里复用同名项目即可唯一命中，不必改动 Backend 场景。
 */
const MOCK_TARGET_PROJECT_NAME = 'Smoke Project'

export interface AgentWorkspaceSandbox {
  workspaceId: number
  projectId: number
  pageId: number
  pageTitle: string
  homeUrl: string
  pageUrl: string
  assetsUrl: string
}

interface NamedEntity {
  id: number
}

/**
 * 构造 AI 沙箱页面源码：不引用 Smoke 工作空间的图片资源，独立空间内可直接预览与校验。
 */
function buildAgentPageContent(headingTitle: string): string {
  return `<template>
  <main class="agent-page">
    <h1 class="text-4xl font-black text-center leading-tight text-slate-900">{{ heading }}</h1>
    <p>agent workspace sandbox preview</p>
  </main>
</template>

<script setup lang="ts">
const heading = '${headingTitle}'
</script>

<style scoped>
.agent-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: #f8fafc;
  color: #0f172a;
}
</style>
`
}

/**
 * 依次创建工作空间、项目和页面，并建立唯一首页路由；任一步失败立即抛出可读错误。
 */
async function createAgentWorkspace(
  api: APIRequestContext,
  suffix: string,
): Promise<{ workspace: NamedEntity; project: NamedEntity; page: NamedEntity; pageTitle: string }> {
  const workspaceResponse = await api.post('/api/workspaces', {
    data: {
      name: `${AGENT_WORKSPACE_NAMESPACE}-${suffix}`,
      description: 'E2E 内容助手用例专属工作空间，用于隔离工作空间级会话与在途 Run。',
      status: 'active',
    },
  })
  if (!workspaceResponse.ok()) {
    throw new Error(`夹具工作空间创建失败：HTTP ${workspaceResponse.status()} ${await workspaceResponse.text()}`)
  }
  const workspace = (await workspaceResponse.json()) as NamedEntity

  const projectResponse = await api.post('/api/projects', {
    data: {
      workspace_id: workspace.id,
      name: MOCK_TARGET_PROJECT_NAME,
      description: 'E2E 内容助手用例专属项目，名称与 mock 页面场景的目标项目名一致。',
    },
  })
  if (!projectResponse.ok()) {
    throw new Error(`夹具项目创建失败：HTTP ${projectResponse.status()} ${await projectResponse.text()}`)
  }
  const project = (await projectResponse.json()) as NamedEntity

  const pageTitle = `Agent 对话页 ${suffix}`
  const pageResponse = await api.post('/api/pages', {
    data: {
      workspace_id: workspace.id,
      project_id: project.id,
      title: pageTitle,
      file_type: 'vue',
      summary: 'E2E 内容助手用例的焦点页面。',
      page_content: buildAgentPageContent(pageTitle),
    },
  })
  if (!pageResponse.ok()) {
    throw new Error(`夹具页面创建失败：HTTP ${pageResponse.status()} ${await pageResponse.text()}`)
  }
  const page = (await pageResponse.json()) as NamedEntity

  // 页面写入的外部任务会渲染候选页，项目至少要有一个页面路由。
  const routeResponse = await api.put(`/api/projects/${project.id}/routes`, {
    data: {
      routes: [{
        route_type: 'page',
        route: 'home',
        order: 0,
        hidden: false,
        page_id: page.id,
      }],
    },
  })
  if (!routeResponse.ok()) {
    throw new Error(`夹具项目路由创建失败：HTTP ${routeResponse.status()} ${await routeResponse.text()}`)
  }

  return { workspace, project, page, pageTitle }
}

/**
 * 最佳努力归档页面、项目与工作空间；归档失败只追加附件，不覆盖原始测试失败。
 */
async function bestEffortArchive(
  api: APIRequestContext,
  ids: { workspaceId?: number; projectId?: number; pageId?: number },
  testInfo: TestInfo,
): Promise<void> {
  const failures: string[] = []
  const steps: Array<{ path: string; label: string; id?: number }> = [
    { path: 'pages', label: '页面', id: ids.pageId },
    { path: 'projects', label: '项目', id: ids.projectId },
    { path: 'workspaces', label: '工作空间', id: ids.workspaceId },
  ]
  for (const step of steps) {
    if (step.id === undefined) continue
    const response = await api.patch(`/api/${step.path}/${step.id}`, { data: { status: 'archived' } }).catch(error => error)
    if (response instanceof Error || !response.ok()) {
      failures.push(`${step.label} ${step.id} 归档失败：${response instanceof Error ? response.message : `HTTP ${response.status()}`}`)
    }
  }
  if (failures.length) {
    await testInfo.attach('agent-workspace-teardown-issues', {
      contentType: 'text/plain',
      body: failures.join('\n'),
    })
  }
}

/** AI 用例数据夹具：每个用例一套独立空间，teardown 后其它 project 看不到本用例的会话与 Run。 */
export const test = base.extend<{ agentWorkspace: AgentWorkspaceSandbox }>({
  agentWorkspace: async ({ context }, use, testInfo) => {
    const api = context.request
    const created: { workspaceId?: number; projectId?: number; pageId?: number } = {}
    try {
      // 后缀取 workerIndex + UUID 前 8 位：并行唯一，同时控制名称长度。
      const suffix = `w${testInfo.workerIndex}-${randomUUID().slice(0, 8)}`
      const { workspace, project, page, pageTitle } = await createAgentWorkspace(api, suffix)
      created.workspaceId = workspace.id
      created.projectId = project.id
      created.pageId = page.id

      await use({
        workspaceId: workspace.id,
        projectId: project.id,
        pageId: page.id,
        pageTitle,
        homeUrl: `/workspaces/${workspace.id}/home`,
        pageUrl: `/workspaces/${workspace.id}/projects/${project.id}/pages/${page.id}`,
        assetsUrl: `/workspaces/${workspace.id}/assets`,
      })
    } finally {
      await bestEffortArchive(api, created, testInfo)
    }
  },
})

export { expect }
