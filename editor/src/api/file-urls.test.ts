/** 文件功能：验证私有文件跨入口鉴权修复，覆盖嵌套 DTO、文件类型边界和版本参数保留。 */
import { describe, expect, it } from 'vitest'

import { buildFileDownloadUrl, normalizeAuthenticatedFileUrls, resolveAuthenticatedFileUrl } from '@/api/file-urls'

describe('authenticated file urls', () => {
  it('将公开基址生成的截图和资源文件对齐同源 API，并保留版本与下载参数', () => {
    expect(resolveAuthenticatedFileUrl('http://127.0.0.1:8000/api/pages/561/screenshots/latest/content?download=1', '/api'))
      .toBe('/api/pages/561/screenshots/latest/content?download=1')
    expect(resolveAuthenticatedFileUrl('http://127.0.0.1:8000/api/workspaces/21/assets/470/file?hash=abc#part', '/api'))
      .toBe('/api/workspaces/21/assets/470/file?hash=abc#part')
  })

  it('显式配置的 API 基址与网关路径前缀也应作为文件访问入口', () => {
    expect(resolveAuthenticatedFileUrl('https://old-api.example/api/workspaces/21/assets/by-hash/abc', 'https://api.example/gateway/api/'))
      .toBe('https://api.example/gateway/api/workspaces/21/assets/by-hash/abc')
  })

  it('第三方文件、预览票据与相似业务路由不应被改写', () => {
    const urls = [
      'https://cdn.example/picture.png', 'blob:http://localhost:5173/file',
      'http://127.0.0.1:8000/preview/artifacts/artifact?token=secret',
      'http://127.0.0.1:8000/api/pages/561',
      'http://127.0.0.1:8000/api/pages/561/screenshots/latest/content/extra',
    ]
    urls.forEach(url => expect(resolveAuthenticatedFileUrl(url, '/api')).toBe(url))
  })

  it('分页、主题嵌套字体和资源 DTO 都应修正，源码与普通 url 字段保持原样', () => {
    const file = 'http://127.0.0.1:8000/api/workspaces/21/assets/470/file?hash=abc'
    const screenshot = 'http://127.0.0.1:8000/api/pages/561/screenshots/latest/content'
    const data = { items: [{ id: 470, workspace_id: 21, file_hash: 'abc', url: file }],
      screenshot_url: screenshot, first_page_screenshot_url: screenshot,
      theme: { faces: [{ asset_url: file }], logo_asset: { id: 470, asset_type: 'image', original_name: 'logo.png', url: file } },
      url: file, page_content: `<img src="${file}">` }
    normalizeAuthenticatedFileUrls(data, '/api')
    expect(data.items[0]?.url).toBe('/api/workspaces/21/assets/470/file?hash=abc')
    expect(data.theme.faces[0]?.asset_url).toBe('/api/workspaces/21/assets/470/file?hash=abc')
    expect(data.theme.logo_asset.url).toBe('/api/workspaces/21/assets/470/file?hash=abc')
    expect(data.screenshot_url).toBe('/api/pages/561/screenshots/latest/content')
    expect(data.first_page_screenshot_url).toBe(data.screenshot_url)
    expect(data.url).toBe(file)
    expect(data.page_content).toBe(`<img src="${file}">`)
  })

  it('二进制响应与空响应保持原样', () => {
    const blob = new Blob(['png'], { type: 'image/png' })
    normalizeAuthenticatedFileUrls(blob, '/api')
    normalizeAuthenticatedFileUrls(null, '/api')
    expect(blob.size).toBe(3)
  })

  it('资源下载不得把 download 参数拼进 hash 值', () => {
    const url = new URL(buildFileDownloadUrl('/api/workspaces/21/assets/470/file?hash=abc#part'))
    expect(url.searchParams.get('hash')).toBe('abc')
    expect(url.searchParams.get('download')).toBe('1')
    expect(url.hash).toBe('#part')
  })
})
