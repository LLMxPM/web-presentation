/**
 * 文件功能：生成预览入口的友好错误文档，在应用启动前向 iframe 宿主回传结构化错误。
 */
import { PAGE_PREVIEW_ERROR_EVENT } from '../shared/page-preview'
import { COMPONENT_PREVIEW_ERROR_EVENT } from '../shared/component-preview'

export interface PreviewErrorDocumentOptions {
  statusCode: number
  code: string
  message: string
  artifactId?: string
  workbenchUrl?: string
}

/** 输出无凭证错误页；只有带 artifact 的文档入口才通知宿主，模块错误不执行脚本。 */
export function buildPreviewErrorDocument(options: PreviewErrorDocumentOptions): string {
  const invalid = ['PREVIEW_CONTEXT_INVALID', 'PREVIEW_CONTEXT_REQUIRED', 'ARTIFACT_NOT_FOUND'].includes(options.code)
  const title = invalid ? '预览链接已失效' : '预览暂时无法打开'
  const message = invalid ? '请返回工作台重新生成预览。' : '请稍后重试，或返回工作台重新生成预览。'
  const payload = serializeScript({
    version: 1, artifactId: options.artifactId, code: options.code, message: `${title}，${message}`,
  })
  const events = serializeScript([PAGE_PREVIEW_ERROR_EVENT, COMPONENT_PREVIEW_ERROR_EVENT])
  const notify = options.artifactId ? `<script>
if (window.parent !== window) {
  const payload = ${payload};
  for (const type of ${events}) window.parent.postMessage({ type, payload }, '*');
}
</script>` : ''
  const workbench = options.workbenchUrl && /^https?:\/\//.test(options.workbenchUrl)
    ? `<a href="${escapeHtml(options.workbenchUrl)}" target="_top">返回工作台</a>` : ''
  const retry = invalid ? '' : '<button type="button" onclick="window.location.reload()">重试加载</button>'
  return `<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>${title}</title>
<style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f8fafc;color:#0f172a;font:14px/1.7 system-ui,"Microsoft YaHei",sans-serif}
main{box-sizing:border-box;width:min(100% - 32px,520px);padding:32px;border:1px solid #e2e8f0;border-radius:12px;background:white}
h1{font-size:22px;margin:0 0 12px}p{color:#475569}.actions{display:flex;flex-wrap:wrap;gap:12px;margin-top:24px}
a,button{padding:8px 16px;border:1px solid #cbd5e1;border-radius:6px;background:white;color:inherit;font:inherit;cursor:pointer;text-decoration:none}
a{background:#0f172a;color:white}a:focus-visible,button:focus-visible{outline:2px solid #2563eb;outline-offset:3px}
details{margin-top:20px;color:#64748b;overflow-wrap:anywhere}
</style></head><body><main><h1>${title}</h1><p>${message}</p><div class="actions">${workbench}${retry}</div>
<details><summary>错误详情</summary><p>HTTP ${options.statusCode} · ${escapeHtml(options.code)}</p>
<p>${escapeHtml(options.message)}</p></details></main>${notify}</body></html>`
}

/** 转义错误文本与链接属性，避免详情破坏页面结构。 */
function escapeHtml(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

/** 转义内联 JSON，避免 artifact 标识闭合 script 标签。 */
function serializeScript(value: unknown): string {
  return JSON.stringify(value).replace(/</g, '\\u003c').replace(/>/g, '\\u003e').replace(/&/g, '\\u0026')
}
