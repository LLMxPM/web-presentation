/** 文件功能：校验 Gateway Nginx 配置可解析，且预览池具备多副本、摘流与 Upgrade 透传结构。 */
import fs from 'node:fs'
import { expect, it } from 'vitest'

const confPath = 'deploy/docker/nginx/web-presentation.conf'

/** 读取 Gateway Nginx 配置原文。 */
function readGatewayConf(): string {
  return fs.readFileSync(confPath, 'utf8')
}

/** 去掉注释行后按花括号深度校验配置块是否闭合，捕获截断/嵌套错误。 */
function assertBraceBalance(source: string): void {
  let depth = 0
  for (const line of source.split('\n')) {
    const code = line.replace(/#.*$/, '')
    for (const char of code) {
      if (char === '{') depth += 1
      if (char === '}') depth -= 1
      expect(depth, `花括号不平衡：${line}`).toBeGreaterThanOrEqual(0)
    }
  }
  expect(depth, '配置结尾花括号未闭合').toBe(0)
}

it('Gateway Nginx 配置可解析且括号闭合', () => {
  const source = readGatewayConf()
  expect(source.length).toBeGreaterThan(0)
  assertBraceBalance(source)
  // map / upstream / server 顶层块必须成对出现。
  expect(source).toMatch(/\bmap\s+\$\w+\s+\$\w+\s*\{/)
  expect(source).toMatch(/\bupstream\s+\w+\s*\{/)
  expect(source).toMatch(/\bserver\s*\{/)
})

it('预览池应为可更新的多实例 upstream，并带失败摘流参数', () => {
  const source = readGatewayConf()
  const upstreamMatch = source.match(/upstream\s+runtime_preview_pool\s*\{([\s\S]*?)\n\}/)
  expect(upstreamMatch, '缺少 upstream runtime_preview_pool').toBeTruthy()
  const body = upstreamMatch![1]

  // 至少一个在役实例；每个未注释的 server 声明都应带 max_fails/fail_timeout 被动摘流。
  const activeServers = body
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.startsWith('server '))
  expect(activeServers.length).toBeGreaterThanOrEqual(1)
  for (const line of activeServers) {
    expect(line, `实例声明缺少摘流参数：${line}`).toMatch(/max_fails=\d+/)
    expect(line, `实例声明缺少摘流参数：${line}`).toMatch(/fail_timeout=\S+/)
  }

  // 多副本就绪：保留第二个预览实例示例（注释形态），便于扩容时取消注释。
  expect(body).toMatch(/#\s*server\s+runtime-preview-2:7373/)
})

it('公开预览路由应走预览池，且保留 Upgrade 透传与失败转移', () => {
  const source = readGatewayConf()

  // WebSocket Upgrade 透传映射仍需存在。
  expect(source).toMatch(/map\s+\$http_upgrade\s+\$connection_upgrade/)
  expect(source).toContain("default upgrade;")

  // 所有原 runtime 直连都应切换到预览池，不得残留单实例 proxy_pass。
  expect(source).toContain('proxy_pass http://runtime_preview_pool;')
  expect(source).not.toMatch(/proxy_pass\s+http:\/\/runtime:7373/)

  // 失败摘流后把可重试请求交给其它副本。
  expect(source).toMatch(/proxy_next_upstream\s+error\s+timeout\s+http_502\s+http_503\s+http_504/)

  // Upgrade / Connection 头必须出现在预览代理 location 中。
  const runtimeLocation = source.match(/location\s+\/runtime\/\s*\{[\s\S]*?\n\s*\}/)
  expect(runtimeLocation).toBeTruthy()
  expect(runtimeLocation![0]).toContain('proxy_set_header Upgrade $http_upgrade;')
  expect(runtimeLocation![0]).toContain('proxy_set_header Connection $connection_upgrade;')
  expect(runtimeLocation![0]).toContain('proxy_pass http://runtime_preview_pool;')
})
