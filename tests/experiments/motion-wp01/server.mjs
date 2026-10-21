// 文件功能：WP01 静态包与跨域受保护素材的临时服务器，仅监听回环随机端口。
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'

/** 提供仅限已知文件的 HEAD/Range/CORS；票据先于范围响应，记录无凭证拒绝和范围请求。 */
export async function serve(directory, { protectedAssets = false, origin = '' } = {}) {
  const requests = []
  const server = createServer(async (request, response) => {
    const url = new URL(request.url, 'http://127.0.0.1')
    if (origin) { response.setHeader('Access-Control-Allow-Origin', origin); response.setHeader('Vary', 'Origin') }
    if (url.pathname === '/favicon.ico') { response.writeHead(204); response.end(); return }
    if (protectedAssets && url.searchParams.get('ticket') !== 'wp01-fixture') { requests.push({ method: request.method, status: 403 }); response.writeHead(403); response.end(); return }
    if (!/^\/[\w.-]+$/.test(url.pathname)) { response.writeHead(404); response.end(); return }
    try {
      const data = await readFile(join(directory, url.pathname.slice(1)))
      const mime = url.pathname.endsWith('.js') ? 'text/javascript' : url.pathname.endsWith('.wav') ? 'audio/wav' : url.pathname.endsWith('.webm') ? 'video/webm' : url.pathname.endsWith('.html') ? 'text/html' : 'model/gltf-binary'
      const headers = { 'Content-Type': mime, 'Accept-Ranges': 'bytes', 'Cache-Control': 'no-store', ...(origin ? { 'Access-Control-Allow-Origin': origin, 'Vary': 'Origin' } : {}) }
      const range = request.headers.range?.match(/^bytes=(\d+)-(\d*)$/)
      const start = range ? Number(range[1]) : 0, end = range?.[2] ? Math.min(data.length - 1, Number(range[2])) : data.length - 1
      const status = range ? 206 : 200
      if (start > end) { response.writeHead(416, { 'Content-Range': `bytes */${data.length}` }); response.end(); return }
      if (range) headers['Content-Range'] = `bytes ${start}-${end}/${data.length}`
      headers['Content-Length'] = end - start + 1
      requests.push({ method: request.method, status, range: request.headers.range ?? null, file: url.pathname })
      response.writeHead(status, headers); response.end(request.method === 'HEAD' ? undefined : data.subarray(start, end + 1))
    } catch { response.writeHead(404); response.end() }
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  return { url: `http://127.0.0.1:${server.address().port}`, requests, close: () => new Promise(resolve => server.close(resolve)) }
}
