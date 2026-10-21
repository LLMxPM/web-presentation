// 文件功能：只托管独立构建的扁平 HTML/JS/CSS，不提供 Vite、源码或 node_modules。
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

/** 构建器输出固定扁平文件名，逐项读取；随机回环端口由调用方关闭。 */
export async function serveStatic(directory) {
  const requests = [], server = createServer(async (request, response) => {
    const pathname = new URL(request.url, 'http://127.0.0.1').pathname
    const file = pathname === '/' ? 'index.html' : pathname.slice(1)
    if (!/^[\w.-]+\.(html|js|css)$/.test(file)) { response.writeHead(404); response.end(); return }
    try {
      const bytes = await readFile(resolve(directory, file)), ext = file.split('.').at(-1)
      requests.push(file)
      response.writeHead(200, { 'Content-Type': { html: 'text/html', js: 'text/javascript', css: 'text/css' }[ext], 'Cache-Control': 'no-store' })
      response.end(bytes)
    } catch { response.writeHead(404); response.end() }
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  return { url: `http://127.0.0.1:${server.address().port}`, requests, close: () => new Promise(resolve => server.close(resolve)) }
}
