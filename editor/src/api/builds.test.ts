/**
 * 文件功能：验证项目构建 API 封装的产物下载预检、原生下载触发与删除请求路径。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { deleteMock, headMock, apiBaseMock } = vi.hoisted(() => ({
  deleteMock: vi.fn(),
  headMock: vi.fn(),
  apiBaseMock: vi.fn(() => '/api'),
}))

vi.mock('@/api/http', () => ({
  http: {
    delete: deleteMock,
    head: headMock,
  },
  resolveApiBaseUrl: apiBaseMock,
}))

import { deleteProjectBuildArtifact, downloadProjectBuildArtifact } from '@/api/builds'

describe('builds api', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    deleteMock.mockResolvedValue({ status: 204 })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('应按项目与任务 ID 删除构建产物', async () => {
    await deleteProjectBuildArtifact(3, 12)

    expect(deleteMock).toHaveBeenCalledWith('/projects/3/build-jobs/12/artifact')
  })

  it('应在 HEAD 预检通过后交给浏览器原生下载', async () => {
    headMock.mockResolvedValue({
      headers: { 'content-disposition': 'attachment; filename="project-3-build-12.zip"' },
    })
    const clicked: HTMLAnchorElement[] = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this)
    })

    await downloadProjectBuildArtifact(3, 12)

    expect(headMock).toHaveBeenCalledWith('/projects/3/build-jobs/12/artifact')
    expect(clicked).toHaveLength(1)
    expect(clicked[0]?.getAttribute('href')).toBe('/api/projects/3/build-jobs/12/artifact')
    expect(clicked[0]?.download).toBe('project-3-build-12.zip')
    // 触发后必须移除临时节点，避免页面不断堆积空 a 标签。
    expect(document.querySelectorAll('a')).toHaveLength(0)
  })

  it('应在缺少响应头时回落到稳定文件名', async () => {
    headMock.mockResolvedValue({ headers: {} })
    const clicked: HTMLAnchorElement[] = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this)
    })

    await downloadProjectBuildArtifact(7, 21)

    expect(clicked[0]?.download).toBe('project-7-build-21.zip')
  })

  it('API 挂在根路径时下载地址应与 axios 拼接结果一致', async () => {
    // VITE_API_BASE_URL="/" 表示接口就在根路径：此时前缀为空是正确结果，
    // 补 /api 会让下载与其它请求分叉到不同路由。
    apiBaseMock.mockReturnValue('/')
    headMock.mockResolvedValue({ headers: {} })
    const clicked: HTMLAnchorElement[] = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this)
    })

    await downloadProjectBuildArtifact(3, 12)

    expect(clicked[0]?.getAttribute('href')).toBe('/projects/3/build-jobs/12/artifact')
    apiBaseMock.mockReturnValue('/api')
  })

  it('HEAD 预检失败时不应触发下载', async () => {
    headMock.mockRejectedValue(new Error('构建产物不存在'))
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    let caught: unknown = null
    try {
      await downloadProjectBuildArtifact(3, 12)
    } catch (error) {
      caught = error
    }

    expect((caught as Error | null)?.message).toBe('构建产物不存在')
    expect(clickSpy).not.toHaveBeenCalled()
  })
})
