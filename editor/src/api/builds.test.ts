/**
 * 文件功能：验证项目构建 API 封装的产物删除请求路径。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { deleteMock } = vi.hoisted(() => ({
  deleteMock: vi.fn(),
}))

vi.mock('@/api/http', () => ({
  http: {
    delete: deleteMock,
  },
}))

import { deleteProjectBuildArtifact } from '@/api/builds'

describe('builds api', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    deleteMock.mockResolvedValue({ status: 204 })
  })

  it('应按项目与任务 ID 删除构建产物', async () => {
    await deleteProjectBuildArtifact(3, 12)

    expect(deleteMock).toHaveBeenCalledWith('/projects/3/build-jobs/12/artifact')
  })
})
