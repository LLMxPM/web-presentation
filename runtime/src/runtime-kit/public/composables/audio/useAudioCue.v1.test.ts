// @vitest-environment jsdom
/**
 * 文件功能：验证公开 useAudioCue 在无 shell provider 与非法输入时稳定 no-op。
 */

import { createApp, defineComponent } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'

import { useAudioCue } from './useAudioCue.v1'

const mounted: ReturnType<typeof createApp>[] = []

afterEach(() => {
  mounted.splice(0).forEach(app => app.unmount())
  document.body.innerHTML = ''
})

/** 在独立组件中调用公开 composable。 */
function mountComposable(): ReturnType<typeof useAudioCue> {
  let api: ReturnType<typeof useAudioCue> | undefined
  const root = document.createElement('div')
  document.body.append(root)
  const app = createApp(defineComponent({
    setup() {
      api = useAudioCue()
      return () => null
    },
  }))
  app.mount(root)
  mounted.push(app)
  return api!
}

describe('useAudioCue.v1', () => {
  it('没有 shell provider 时返回 unavailable，不抛异常', () => {
    const { playCue } = mountComposable()

    expect(playCue('interaction.confirm')).toBe('unavailable')
    expect(playCue('transition.forward')).toBe('unavailable')
  })

  it('空 key 直接 no-op，不要求页面处理异常', () => {
    const { playCue } = mountComposable()

    expect(playCue('')).toBe('unavailable')
    expect(playCue('   ')).toBe('unavailable')
  })
})
