/**
 * 文件功能：为 C3 实机验收用例提供沙箱页面与放映搭建工具，复用真实 Backend API 创建页面、路由和预览产物。
 *
 * 所有写操作都落在夹具分配的专属项目内，用例结束由夹具归档；这里只负责构造、发布与进入放映。
 */
import { expect, type APIRequestContext, type Frame, type FrameLocator, type Page } from '@playwright/test'

/** 沙箱项目的最小字段，与 visualEditSandbox 夹具保持一致。 */
export interface SandboxRef {
  workspaceId: number
  projectId: number
}

/** 放映配置只提交 schema 4 允许的字段。 */
export interface SlideshowOptions {
  mode?: 'manual' | 'timer' | 'scene_end'
  delayMs?: number
  loop?: boolean
  completionDelayMs?: number
}

/** 页面路由条目，order 决定放映顺序。 */
export interface RouteEntry {
  route: string
  pageId: number
}

/** 创建页面并返回页面 ID；失败时直接抛出可读响应。 */
export async function createSandboxPage(
  api: APIRequestContext,
  sandbox: SandboxRef,
  title: string,
  source: string,
): Promise<number> {
  const response = await api.post('/api/pages', {
    data: {
      workspace_id: sandbox.workspaceId,
      project_id: sandbox.projectId,
      title,
      file_type: 'vue',
      page_content: source,
    },
  })
  expect(response.ok(), await response.text()).toBeTruthy()
  return Number((await response.json()).id)
}

/** 归档临时页面；失败不影响原始断言结果。 */
export async function archiveSandboxPage(api: APIRequestContext, pageId: number): Promise<void> {
  await api.patch(`/api/pages/${pageId}`, { data: { status: 'archived' } }).catch(() => undefined)
}

/** 写入项目路由并生成新的预览产物，返回可直接打开的预览地址。 */
export async function publishRoutes(
  api: APIRequestContext,
  projectId: number,
  entries: RouteEntry[],
): Promise<string> {
  const routes = await api.put(`/api/projects/${projectId}/routes`, {
    data: {
      routes: entries.map((entry, index) => ({
        route_type: 'page',
        route: entry.route,
        order: index,
        hidden: false,
        page_id: entry.pageId,
      })),
    },
  })
  expect(routes.ok(), await routes.text()).toBeTruthy()
  const artifact = await api.post(`/api/projects/${projectId}/preview-artifacts`, { data: {} })
  expect(artifact.ok(), await artifact.text()).toBeTruthy()
  return (await artifact.json()).preview_url as string
}

/** 写入 schema 4 放映配置；不提交任何已删除的旧字段。 */
export async function configureSlideshow(
  api: APIRequestContext,
  projectId: number,
  options: SlideshowOptions = {},
): Promise<void> {
  const response = await api.patch(`/api/projects/${projectId}`, {
    data: {
      slideshow: {
        transition: { effect: 'none', duration_ms: 0 },
        advance: {
          mode: options.mode ?? 'manual',
          delay_ms: options.delayMs ?? 5000,
          completion_delay_ms: options.completionDelayMs ?? 300,
        },
        loop: options.loop ?? false,
      },
    },
  })
  expect(response.ok(), await response.text()).toBeTruthy()
}

/** 上传一个资源到沙箱工作空间，返回逻辑名。 */
export async function uploadSandboxAsset(
  api: APIRequestContext,
  workspaceId: number,
  asset: { name: string; type: string; mimeType: string; fileName: string; buffer: Buffer },
): Promise<void> {
  const response = await api.post(`/api/workspaces/${workspaceId}/assets/upload`, {
    multipart: {
      file: { name: asset.fileName, mimeType: asset.mimeType, buffer: asset.buffer },
      asset_type: asset.type,
      tags: '[]',
      name: asset.name,
    },
  })
  expect(response.ok(), await response.text()).toBeTruthy()
}

/** 打开预览产物并进入放映，返回运行时 iframe 与控制条。 */
export async function enterPlayback(
  page: Page,
  previewUrl: string,
): Promise<{ runtime: FrameLocator; controls: ReturnType<FrameLocator['getByRole']> }> {
  await page.goto(previewUrl)
  const runtime = page.frameLocator('iframe#preview')
  await runtime.getByRole('button', { name: '进入放映' }).click()
  const controls = runtime.getByRole('group', { name: '放映控制' })
  await expect(controls).toBeVisible()
  return { runtime, controls }
}

/**
 * 取运行时 iframe 的 Frame 句柄，供需要 evaluate 的探针使用。
 * FrameLocator 没有 evaluate，必须按地址从 page.frames() 里定位同源预览帧。
 */
export async function runtimeFrame(page: Page): Promise<Frame> {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    const frame = page
      .frames()
      .find(candidate => candidate !== page.mainFrame() && /preview\.localhost|__preview|:7373/.test(candidate.url()))
    if (frame) return frame
    await page.waitForTimeout(200)
  }
  throw new Error('未找到 Runtime 预览 iframe，无法安装浏览器侧探针')
}
