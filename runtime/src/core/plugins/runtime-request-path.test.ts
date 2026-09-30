/** 文件功能：验证版本化 Vite base 下固定 Runtime 入口及资源路径解析，防止截图误入 SPA 门禁。 */
import { describe, expect, it } from 'vitest'
import { stripRuntimeRequestBase } from './runtime-request-path'
import { shouldBlockStandalonePreviewRequest } from './runtime-standalone-preview-gate'

describe('Runtime 固定入口与版本化资源挂载', () => {
  const base = '/runtime/__runtime_version/v1.fixture/'
  it.each([
    ['/runtime/__preview?artifact=fixture', '/__preview?artifact=fixture'],
    ['/runtime/__runtime_version/v1.fixture/@runtime-preview/id/Page.vue?ctx=fixture', '/@runtime-preview/id/Page.vue?ctx=fixture'],
    ['/__preview?artifact=fixture', '/__preview?artifact=fixture'],
    ['/runtime?artifact=fixture', '/?artifact=fixture'],
    ['/other/__preview', '/other/__preview'],
  ])('解析 %s 并保留查询参数', (url, expected) => {
    expect(stripRuntimeRequestBase(url, base)).toBe(expected)
  })
  it('版本化 base 下固定截图入口继续交给 SaaS 验签，独立导航继续拒绝', () => {
    expect(shouldBlockStandalonePreviewRequest({ url: '/runtime/__preview', headers: { 'sec-fetch-mode': 'navigate' } }, base)).toBe(false)
    expect(shouldBlockStandalonePreviewRequest({ url: '/runtime/arbitrary-page', headers: { 'sec-fetch-mode': 'navigate' } }, base)).toBe(true)
  })
})
