// @vitest-environment jsdom
/* eslint-disable vue/component-definition-name-casing */

/**
 * 文件用途：验证应用品牌图标组件按静态图标配置渲染原始图片资源。
 */

import { createApp, nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import AppBrandIcon from './AppBrandIcon.vue'

const getIconConfigMock = vi.hoisted(() => vi.fn())

vi.mock('@/core/utils/icon-registry', () => ({
  getIconConfig: getIconConfigMock,
}))

beforeEach(() => {
  getIconConfigMock.mockResolvedValue({
    type: 'static',
    src: 'img/icon/slider.svg',
    description: 'Slider icon',
  })
})

afterEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

describe('AppBrandIcon', () => {
  it('应直接渲染静态图片地址并保留原始颜色', async () => {
    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(AppBrandIcon, {
      name: 'slider',
      alt: '项目标题',
      size: 24,
    })

    app.mount(host)
    await Promise.resolve()
    await nextTick()

    const image = host.querySelector('img.app-brand-icon') as HTMLImageElement | null
    expect(getIconConfigMock).toHaveBeenCalledWith('slider')
    expect(image).not.toBeNull()
    expect(image?.getAttribute('src')).toBe('./img/icon/slider.svg')
    expect(image?.getAttribute('alt')).toBe('项目标题')
    expect(image?.style.width).toBe('24px')
    expect(host.querySelector('svg')).toBeNull()

    app.unmount()
  })
})
