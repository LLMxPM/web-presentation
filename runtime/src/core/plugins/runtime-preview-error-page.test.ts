/** 文件功能：验证预览错误文档在应用启动前通知宿主，以及文本和内联脚本的安全转义。 */
import { describe, expect, it } from 'vitest'

import { buildPreviewErrorDocument } from './runtime-preview-error-page'

describe('预览错误文档', () => {
  it('失效文档包含当前 artifact、错误码、双协议通知和工作台出口', () => {
    const html = buildPreviewErrorDocument({
      statusCode: 401, code: 'PREVIEW_CONTEXT_INVALID', message: '原始错误',
      artifactId: 'rt_1', workbenchUrl: 'https://editor.example/workspaces/1/home',
    })
    expect(html).toContain('预览链接已失效')
    expect(html).toContain('page-preview:error')
    expect(html).toContain('component-preview:error')
    expect(html).toContain('"artifactId":"rt_1"')
    expect(html).toContain('"code":"PREVIEW_CONTEXT_INVALID"')
    expect(html).toContain('返回工作台')
    expect(html).not.toContain('window.location.reload()')
  })

  it('模块错误不发送宿主消息，保留版本失配状态和可重试动作', () => {
    const html = buildPreviewErrorDocument({ statusCode: 409, code: 'PREVIEW_VERSION_SKEW', message: '版本不一致' })
    expect(html).toContain('HTTP 409')
    expect(html).toContain('重试加载')
    expect(html).not.toContain('postMessage')
  })

  it('恶意 artifact、错误详情和非 HTTP 工作台链接不能注入可执行内容', () => {
    const html = buildPreviewErrorDocument({
      statusCode: 401, code: 'PREVIEW_CONTEXT_INVALID', message: '<img src=x onerror=alert(1)>',
      artifactId: '</script><script>alert(2)</script>', workbenchUrl: 'javascript:alert(3)',
    })
    expect(html).not.toContain('<img src=x')
    expect(html).not.toContain('</script><script>')
    expect(html).not.toContain('javascript:')
    expect(html).toContain('\\u003c/script\\u003e')
  })
})
