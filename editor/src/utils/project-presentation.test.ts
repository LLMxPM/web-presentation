/** 文件功能：验证项目放映入口先占位窗口、再导航新快照以及弹窗被阻止时的错误处理。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createProjectPreviewArtifact } from '@/api/preview'
import { openProjectPresentation } from './project-presentation'

vi.mock('@/api/preview', () => ({ createProjectPreviewArtifact: vi.fn() }))

const mockedCreate = vi.mocked(createProjectPreviewArtifact)
const PREVIEW_URL = 'https://preview.test/artifacts/one'

interface FakePopup {
  closed: boolean
  location: { replace: ReturnType<typeof vi.fn> }
  close: ReturnType<typeof vi.fn>
}

function createPopup(): FakePopup {
  return { closed: false, location: { replace: vi.fn() }, close: vi.fn() }
}

beforeEach(() => {
  mockedCreate.mockReset()
  mockedCreate.mockResolvedValue({ preview_url: PREVIEW_URL } as never)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('openProjectPresentation', () => {
  it('同步打开占位窗口并导航到新建的只读快照', async () => {
    const popup = createPopup()
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(popup as unknown as Window)

    await openProjectPresentation({ projectId: 10 })

    expect(openSpy).toHaveBeenCalledWith('about:blank', '_blank')
    expect(mockedCreate).toHaveBeenCalledWith(10, null)
    expect(popup.location.replace).toHaveBeenCalledWith(PREVIEW_URL)
    expect(popup.close).not.toHaveBeenCalled()
  })

  it('从当前页放映时传递入口路由', async () => {
    const popup = createPopup()
    vi.spyOn(window, 'open').mockReturnValue(popup as unknown as Window)

    await openProjectPresentation({ projectId: 11, entryRoute: '/section/current' })

    expect(mockedCreate).toHaveBeenCalledWith(11, '/section/current')
    expect(popup.location.replace).toHaveBeenCalledWith(PREVIEW_URL)
  })

  it('占位窗口被阻止时回退为新窗口打开预览地址', async () => {
    const fallback = createPopup()
    const openSpy = vi.spyOn(window, 'open')
      .mockReturnValueOnce(null)
      .mockReturnValueOnce(fallback as unknown as Window)

    await openProjectPresentation({ projectId: 12 })

    expect(openSpy).toHaveBeenNthCalledWith(1, 'about:blank', '_blank')
    expect(openSpy).toHaveBeenNthCalledWith(2, PREVIEW_URL, '_blank')
  })

  it('生成失败时关闭占位窗口并抛出错误', async () => {
    const popup = createPopup()
    vi.spyOn(window, 'open').mockReturnValue(popup as unknown as Window)
    mockedCreate.mockRejectedValue(new Error('接口失败'))

    let caught: unknown
    try {
      await openProjectPresentation({ projectId: 13 })
    } catch (error) {
      caught = error
    }
    expect(caught).toBeInstanceOf(Error)
    expect((caught as Error).message).toBe('接口失败')
    expect(popup.close).toHaveBeenCalledTimes(1)
  })

  it('两次打开都被浏览器阻止时提示允许弹窗', async () => {
    vi.spyOn(window, 'open').mockReturnValue(null)
    let caught: unknown
    try {
      await openProjectPresentation({ projectId: 14 })
    } catch (error) {
      caught = error
    }
    expect(caught).toBeInstanceOf(Error)
    expect((caught as Error).message).toContain('浏览器阻止了新窗口')
  })
})
