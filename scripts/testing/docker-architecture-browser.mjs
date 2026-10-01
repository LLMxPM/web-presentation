/** 文件功能：用真实 Chromium iframe 验证同版跨副本、跨版拒绝与 ZIP 站点入口；证据不保存令牌。 */
import { chromium } from '@playwright/test'
import { readFile, writeFile, stat } from 'node:fs/promises'
import { createServer } from 'node:http'
import path from 'node:path'

const [directory, mode = 'same'] = process.argv.slice(2)
if (!directory || !['same', 'single', 'cross', 'build'].includes(mode)) throw new Error('需要演练目录和 same/single/cross/build 场景')
const root = path.resolve(import.meta.dirname, '../..')
const folder = path.resolve(directory)
if (!folder.startsWith(path.join(root, '.tmp', 'docker-architecture') + path.sep)) throw new Error('无效演练目录')
const context = JSON.parse(await readFile(path.join(folder, 'context.json'), 'utf8'))
const output = path.join(root, context.output)
const data = JSON.parse(await readFile(path.join(output, 'seed.json'), 'utf8'))
const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } })
const requests = []
const failedRequests = []
const errors = []
const pending = []
let server

/** 仅记录去掉查询参数的路径、版本及响应码，避免 preview token 进入证据。 */
page.on('response', response => {
  pending.push((async () => {
    const url = new URL(response.url())
    const headers = await response.allHeaders()
    let code
    let bodyError
    let codeSource
    if (response.status() === 409) {
      try { code = (await response.json()).code; codeSource = 'browser_response' } catch (error) {
        bodyError = error.message.replace(/\?.*$/s, '?[redacted]')
        // Chromium 对拒绝加载的 script/CSS 可只提供状态头、不保留正文。
        // 用该浏览器实际发出的原 URL 再读错误详情，独立标记来源，不构造版本头。
        const detail = await page.request.get(response.url())
        if (detail.status() !== 409 || detail.headers()['x-runtime-version-fingerprint'] !== headers['x-runtime-version-fingerprint']) throw new Error('版本拒绝复查与浏览器响应不一致')
        code = (await detail.json()).code
        codeSource = 'exact_browser_url_http_replay'
      }
    }
    requests.push({ path: url.pathname, query_keys: [...url.searchParams.keys()], status: response.status(), version: headers['x-runtime-version-fingerprint'], upstream: headers['x-drill-upstream'], code, code_source: codeSource, body_error: bodyError })
  })())
})
page.on('pageerror', error => errors.push(error.message.replace(/\?.*$/s, '?[redacted]')))
page.on('requestfailed', request => failedRequests.push({ path: new URL(request.url()).pathname, error: request.failure()?.errorText }))
const report = { status: 'failed', mode, browser: browser.version(), requests, failed_requests: failedRequests, errors }
try {
  let url
  if (data.preview_gateway_override) {
    // 只改专属容器名对应的回环端口，不修改请求票据、版本头或模块内容。
    await page.route(/^http:\/\/m05_(platform|lite)\//, async route => {
      const requestUrl = new URL(route.request().url())
      await route.continue({ url: new URL(requestUrl.pathname + requestUrl.search, context.origins.gateway).href })
    })
  }
  if (mode === 'build') {
    const latest = JSON.parse(await readFile(path.join(output, 'pipeline-current.json'), 'utf8'))
    const site = path.resolve(output, latest.build_site)
    if (!site.startsWith(output + path.sep)) throw new Error('构建站点超出演练证据目录')
    server = createServer(async (request, response) => {
      try {
        const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname)
        const file = path.resolve(site, '.' + (pathname.endsWith('/') ? pathname + 'index.html' : pathname))
        if (!file.startsWith(site + path.sep)) { response.writeHead(403).end(); return }
        if (!(await stat(file)).isFile()) { response.writeHead(404).end(); return }
        const types = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2' }
        response.setHeader('Content-Type', types[path.extname(file)] || 'application/octet-stream')
        response.end(await readFile(file))
      } catch { response.writeHead(404).end() }
    })
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
    url = `http://127.0.0.1:${server.address().port}/index.html`
    await page.goto(url)
    await page.getByRole('heading', { name: 'Docker architecture probe' }).waitFor({ timeout: 30_000 })
  } else {
    const origin = context.origins.gateway
    const login = await page.request.post(origin + '/api/auth/login', { data: { username: 'admin', password: context.password } })
    if (!login.ok()) throw new Error('测试账号登录失败')
    const pageInfo = await page.request.get(origin + `/api/pages/${data.page_id}`)
    const version = (await pageInfo.json()).current_version_no
    const preview = await page.request.post(origin + `/api/pages/${data.page_id}/versions/${version}/preview-artifact`, { data: {} })
    if (!preview.ok()) throw new Error(`预览创建失败 ${preview.status()}`)
    url = (await preview.json()).preview_url
    if (data.preview_gateway_override) {
      // Docker 服务地址供真实 Renderer 使用；主机 Chromium 经同一入口的回环映射访问。
      const internal = new URL(url)
      if (!['m05_platform', 'm05_lite'].includes(internal.hostname)) throw new Error('预览地址不属于本次专属入口')
      url = new URL(internal.pathname + internal.search, origin).href
      report.preview_address_mapping = { internal_host: internal.hostname, external_origin: origin }
    }
    // 工作台与 iframe 同源；先导航该 Gateway，再替换父页面，避免 about:blank 的 opaque origin。
    await page.goto(origin + '/healthz')
    await page.setContent('<iframe title="architecture-preview" style="width:1920px;height:1080px;border:0"></iframe>')
    await page.locator('iframe').evaluate((element, value) => { element.src = value }, url)
    if (mode === 'same' || mode === 'single') {
      await page.frameLocator('iframe').getByRole('heading', { name: 'Docker architecture probe' }).waitFor({ timeout: 45_000 })
      await page.frameLocator('iframe').getByText('Rendered by Runtime', { exact: true }).waitFor()
    } else {
      await page.waitForResponse(response => response.status() === 409 && new URL(response.url()).pathname.startsWith('/runtime/'), { timeout: 30_000 })
      // 收集同一导航引发的模块、CSS 与 Vite 请求，不给浏览器注入任何期望版本头。
      await page.waitForTimeout(1500)
    }
  }
  if (mode !== 'cross') {
    const frame = mode === 'same' || mode === 'single' ? page.frames().find(item => item.parentFrame()) : page.mainFrame()
    report.page_style = await frame.evaluate(async () => {
      // 目标样式必须真正生效；字体下载和解析也应完成，不能以响应 200 代替可用性。
      await document.fonts.ready
      const style = getComputedStyle(document.querySelector('.probe'))
      return { color: style.color, padding: style.paddingTop, fonts_loading: [...document.fonts].filter(font => font.status === 'loading').length, fonts_error: [...document.fonts].filter(font => font.status === 'error').length }
    })
    if (report.page_style.color !== 'rgb(18, 52, 86)' || report.page_style.padding !== '48px' || report.page_style.fonts_error || report.page_style.fonts_loading) throw new Error('目标 scoped CSS 或字体未实际生效')
    if (data.public_kit) {
      report.public_kit = await frame.evaluate(() => {
        // 构建站点还会渲染缩略图；选择实际最大页面画布，避免把缩略图副本计成公共组件重复。
        const canvas = [...document.querySelectorAll('.probe')].sort((a, b) => b.getBoundingClientRect().width - a.getBoundingClientRect().width)[0]
        return { tables: canvas.querySelectorAll('[data-runtime-kit-table="v1"]').length, text: canvas.querySelector('[data-runtime-kit-table="v1"]')?.textContent, size: canvas.querySelector('[data-kit-size]')?.textContent }
      })
      if (report.public_kit.tables !== 1 || !report.public_kit.text.includes('Kit v1') || report.public_kit.size !== '1920 × 1080') throw new Error('旧版公开 Kit 表格或尺寸能力没有实际生效')
    }
    if (failedRequests.length) throw new Error('浏览器存在失败网络请求')
  }
  const collected = await Promise.allSettled(pending)
  if (collected.some(item => item.status === 'rejected')) throw new Error('响应证据采集失败')
  const relevant = requests.filter(item => item.path.startsWith('/runtime/'))
  if (mode === 'same') {
    const upstreams = [...new Set(relevant.filter(item => item.status === 200).map(item => item.upstream).filter(Boolean))]
    if (upstreams.length < 2) throw new Error('没有证明浏览器子请求跨两个预览副本')
    if (relevant.some(item => item.status >= 400)) throw new Error('同版子请求失败')
    if (errors.length) throw new Error('同版预览产生页面异常')
    const versions = [...new Set(relevant.map(item => item.version).filter(Boolean))]
    if (versions.length !== 1) throw new Error('同版响应身份不一致')
    report.upstreams = upstreams
    report.versions = versions
  } else if (mode === 'cross') {
    // main.ts 已拒绝时不会再触发其 import；CSS 使用 HTML 自然请求的 Tailwind 样式。
    for (const suffix of ['/src/main.ts', '/__preview-tailwind.css', '/@vite/client']) {
      if (!relevant.some(item => item.path.endsWith(suffix) && item.status === 409 && item.code === 'PREVIEW_VERSION_SKEW')) throw new Error(`未覆盖 ${suffix} 的明确版本拒绝`)
    }
    if (await page.frameLocator('iframe').getByRole('heading', { name: 'Docker architecture probe' }).count()) throw new Error('跨版页面意外加载')
  } else if (mode === 'single') {
    if (relevant.some(item => item.status >= 400) || errors.length) throw new Error('单副本预览有失败请求或页面异常')
    report.versions = [...new Set(relevant.map(item => item.version).filter(Boolean))]
  } else if (requests.some(item => item.status >= 400) || errors.length) {
    throw new Error('构建入口加载有失败请求或页面异常')
  }
  await page.screenshot({ path: path.join(output, `browser-${mode}.png`) })
  report.status = 'passed'
  console.log(`浏览器 ${mode} 验证通过；${requests.length} 条脱敏响应记录`)
} catch (error) {
  report.error = error.message
  report.frames = await Promise.all(page.frames().map(async frame => ({
    path: frame.url().startsWith('http') ? new URL(frame.url()).pathname : frame.url(),
    text: (await frame.locator('body').innerText().catch(() => '')).slice(0, 1500).replace(/\b[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b/g, '[redacted-token]'),
  })))
  await page.screenshot({ path: path.join(output, `browser-${mode}-failure.png`) })
  throw error
} finally {
  await Promise.allSettled(pending)
  const reportPath = path.join(output, `browser-${mode}.json`)
  const previous = await readFile(reportPath, 'utf8').catch(() => null)
  if (previous && JSON.parse(previous).status === 'failed') {
    await writeFile(path.join(output, `browser-${mode}-failure-${Date.now()}.json`), previous)
  }
  await writeFile(reportPath, JSON.stringify(report, null, 2))
  await browser.close()
  if (server) await new Promise(resolve => server.close(resolve))
}
