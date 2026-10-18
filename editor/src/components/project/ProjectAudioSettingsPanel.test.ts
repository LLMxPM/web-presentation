// @vitest-environment jsdom
/** 文件功能：验证项目音频面板的资源加载、音量/绑定编辑、试听音量与关闭清理。 */
import { defineComponent, h, ref } from 'vue'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AssetResponse } from '@/types/api'
import { listWorkspaceAssets } from '@/api/assets'
import {
  createAudioSettingsDraft,
  type AudioSettingsDraft,
} from './project-audio-values'
import ProjectAudioSettingsPanel from './ProjectAudioSettingsPanel.vue'

vi.mock('@/api/assets', () => ({
  listWorkspaceAssets: vi.fn(),
}))

/** 记录播放、暂停与音量的 Audio 替身。 */
class FakeAudio {
  static instances: FakeAudio[] = []
  src: string
  volume = 1
  preload = ''
  muted = false
  currentTime = 0
  paused = true
  onended: (() => void) | null = null
  pause = vi.fn((): void => { this.paused = true })
  play = vi.fn((): Promise<void> => {
    this.paused = false
    return Promise.resolve()
  })

  constructor(src: string) {
    this.src = src
    FakeAudio.instances.push(this)
  }
}

const audioAssets = [
  {
    id: 51,
    workspace_id: 3,
    name: '确认音',
    original_name: 'confirm.mp3',
    asset_type: 'audio',
    status: 'active',
    url: '/api/workspaces/3/assets/51/file',
    file_hash: 'hash-51',
  },
] as unknown as AssetResponse[]

const pagedAssets = { items: audioAssets, total: 1, page: 1, page_size: 100 }

/** 根据 API 设置生成面板草稿。 */
function createDraft(): AudioSettingsDraft {
  return createAudioSettingsDraft({
    master_volume_percent: 80,
    narration_volume_percent: 100,
    effects_volume_percent: 25,
    cue_bindings: [
      { key: 'transition.forward', asset_id: 51, gain_percent: 50 },
    ],
  })
}

beforeEach(() => {
  FakeAudio.instances = []
  vi.stubGlobal('Audio', FakeAudio)
  vi.mocked(listWorkspaceAssets).mockResolvedValue(pagedAssets)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('ProjectAudioSettingsPanel', () => {
  it('加载音频资源并显示切页/交互 Cue 与最终音量', async () => {
    render(ProjectAudioSettingsPanel, {
      props: { workspaceId: 3, draft: createDraft() },
    })

    await waitFor(() => expect(screen.getByText('确认音')).toBeInTheDocument())
    expect(screen.getByText('前进切页')).toBeInTheDocument()
    expect(screen.getByText('后退切页')).toBeInTheDocument()
    expect(screen.getByText('最终音量：10%')).toBeInTheDocument()
    expect(listWorkspaceAssets).toHaveBeenCalledWith(3, expect.objectContaining({
      assetType: 'audio',
      status: 'active',
    }))
  })

  it('编辑音量、绑定增益与清空操作都回传完整草稿', async () => {
    const { emitted } = render(ProjectAudioSettingsPanel, {
      props: { workspaceId: 3, draft: createDraft() },
    })
    await waitFor(() => expect(screen.getByText('确认音')).toBeInTheDocument())

    await fireEvent.update(screen.getByLabelText('主音量'), '60')
    let updates = emitted('update:draft') as Array<[AudioSettingsDraft]>
    expect(updates.at(-1)?.[0].masterVolume).toBe('60')
    expect(updates.at(-1)?.[0].transitionForward.assetId).toBe('51')

    await fireEvent.update(screen.getAllByLabelText('绑定增益')[0], '40')
    updates = emitted('update:draft') as Array<[AudioSettingsDraft]>
    expect(updates.at(-1)?.[0].transitionForward.gainPercent).toBe('40')

    await fireEvent.click(screen.getAllByRole('button', { name: '清空' })[0])
    updates = emitted('update:draft') as Array<[AudioSettingsDraft]>
    expect(updates.at(-1)?.[0].transitionForward.assetId).toBe('')
  })

  it('添加交互 Cue 追加空白行，删除交互行移除草稿项', async () => {
    const host = defineComponent({
      setup() {
        const draft = ref(createDraft())
        return () => h(ProjectAudioSettingsPanel, {
          workspaceId: 3,
          draft: draft.value,
          'onUpdate:draft': (value: AudioSettingsDraft) => { draft.value = value },
        })
      },
    })
    render(host)
    await waitFor(() => expect(screen.getByText('确认音')).toBeInTheDocument())

    await fireEvent.click(screen.getByRole('button', { name: '添加交互音效' }))
    expect(screen.getByText('交互音效 1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '删除' })).toBeInTheDocument()

    await fireEvent.click(screen.getByRole('button', { name: '删除' }))
    expect(screen.queryByText('交互音效 1')).not.toBeInTheDocument()
  })

  it('试听按主音量 × 音效音量 × 绑定增益设置音量，并随音量编辑更新', async () => {
    const host = defineComponent({
      setup() {
        const draft = ref(createDraft())
        return () => h(ProjectAudioSettingsPanel, {
          workspaceId: 3,
          draft: draft.value,
          'onUpdate:draft': (value: AudioSettingsDraft) => { draft.value = value },
        })
      },
    })
    render(host)
    await waitFor(() => expect(screen.getByText('确认音')).toBeInTheDocument())

    await fireEvent.click(screen.getAllByRole('button', { name: '试听' })[0])

    expect(FakeAudio.instances).toHaveLength(1)
    expect(FakeAudio.instances[0].src).toBe('/api/workspaces/3/assets/51/file')
    expect(FakeAudio.instances[0].volume).toBeCloseTo(0.1)
    expect(FakeAudio.instances[0].play).toHaveBeenCalledTimes(1)

    await fireEvent.update(screen.getByLabelText('主音量'), '40')
    expect(FakeAudio.instances[0].volume).toBeCloseTo(0.05)

    await fireEvent.click(screen.getByRole('button', { name: '停止试听' }))
    expect(FakeAudio.instances[0].paused).toBe(true)
  })

  it('卸载时停止试听', async () => {
    const view = render(ProjectAudioSettingsPanel, {
      props: { workspaceId: 3, draft: createDraft() },
    })
    await waitFor(() => expect(screen.getByText('确认音')).toBeInTheDocument())
    await fireEvent.click(screen.getAllByRole('button', { name: '试听' })[0])
    const element = FakeAudio.instances[0]

    view.unmount()
    expect(element.pause).toHaveBeenCalled()
  })

  it('空资源与加载失败提供明确状态和重试入口', async () => {
    vi.mocked(listWorkspaceAssets).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 100 })
    const empty = render(ProjectAudioSettingsPanel, {
      props: { workspaceId: 3, draft: createDraft() },
    })
    await waitFor(() => expect(screen.getByText(/还没有可用音频资源/)).toBeInTheDocument())
    empty.unmount()

    vi.mocked(listWorkspaceAssets).mockRejectedValueOnce(new Error('boom'))
    render(ProjectAudioSettingsPanel, {
      props: { workspaceId: 3, draft: createDraft() },
    })
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('boom'))
    vi.mocked(listWorkspaceAssets).mockResolvedValueOnce(pagedAssets)
    await fireEvent.click(screen.getByRole('button', { name: '重试' }))
    await waitFor(() => expect(screen.getByText('确认音')).toBeInTheDocument())
  })
})
