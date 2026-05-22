/**
 * 文件功能：初始化 Vitest 测试环境，注册 DOM 断言扩展能力。
 */
import '@testing-library/jest-dom/vitest'

Object.defineProperty(document, 'queryCommandSupported', {
  value: () => true,
  configurable: true,
})

Object.defineProperty(window.navigator, 'clipboard', {
  value: {
    writeText: () => Promise.resolve(),
  },
  configurable: true,
})

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

Object.defineProperty(window, 'ResizeObserver', {
  value: ResizeObserverMock,
  configurable: true,
})

Object.defineProperty(window, 'matchMedia', {
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
  configurable: true,
})
