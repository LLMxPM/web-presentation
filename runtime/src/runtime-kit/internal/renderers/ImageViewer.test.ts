// @vitest-environment jsdom

/** 文件用途：验证图片加载失败时显示占位，并在地址变化后恢复加载。 */

import { createApp, h, nextTick, ref } from 'vue'
import { afterEach, expect, it } from 'vitest'

import ImageViewer from './ImageViewer.vue'

const mountedApps: Array<ReturnType<typeof createApp>> = []

afterEach(() => {
  for (const app of mountedApps) {
    app.unmount()
  }
  mountedApps.length = 0
  document.body.innerHTML = ''
})

it('资源加载失败时展示回退内容，地址变化后重新显示图片', async () => {
  const source = ref('https://assets.example/missing.png')
  const container = document.createElement('div')
  document.body.appendChild(container)
  const app = createApp({
    setup: () => () => h(ImageViewer, { src: source.value }, {
      fallback: () => h('span', { 'data-testid': 'fallback' }, '图片不可用'),
    }),
  })
  mountedApps.push(app)
  app.mount(container)

  const image = container.querySelector('img')
  expect(image?.dataset.runtimeImageFallback).toBe('true')
  image?.dispatchEvent(new Event('error'))
  await nextTick()

  expect(container.querySelector('img')).toBeNull()
  expect(container.querySelector('[data-testid="fallback"]')?.textContent).toBe('图片不可用')

  source.value = 'https://assets.example/recovered.png'
  await nextTick()
  expect(container.querySelector('img')?.getAttribute('src')).toBe(source.value)
})
