/**
 * 文件用途：生成 Runtime backend build 使用的入口脚本与构建态 index.html。
 */

import type { RuntimePreloadedConfigBundle } from '../shared/runtime-preview'

/**
 * 生成构建态入口脚本文本。
 * 关键约束：
 * 1. 必须先写入 `window.__RUNTIME_PRELOADED_CONFIG__`；
 * 2. 必须使用动态导入启动 `main`，避免静态 import 被 ESM 提前执行；
 * 3. 若入口模块加载失败，需输出清晰错误，便于定位构建产物问题。
 * @param preloadedConfig Backend 下发的构建态预加载配置
 * @returns 构建入口脚本源码
 */
export function createBuildEntrySource(preloadedConfig: RuntimePreloadedConfigBundle): string {
  const serializedConfig = JSON.stringify(preloadedConfig)

  return [
    '/**',
    ' * 文件用途：构建态入口文件，负责注入 build_release 预加载配置并启动 Runtime 应用。',
    ' */',
    `window.__RUNTIME_PRELOADED_CONFIG__ = ${serializedConfig};`,
    "void import('./build-release-main').catch((error) => {",
    "  console.error('构建态入口加载失败', error)",
    '  document.body.innerHTML = `',
    '    <div style="display:flex;justify-content:center;align-items:center;height:100vh;font-family:Segoe UI,PingFang SC,sans-serif;background:#f8fafc;">',
    '      <div style="max-width:720px;padding:32px;text-align:center;color:#dc2626;background:#ffffff;border:1px solid #fecaca;border-radius:16px;box-shadow:0 10px 30px rgba(15,23,42,.08);">',
    '        <h1 style="margin:0 0 12px;font-size:28px;">Runtime 构建入口加载失败</h1>',
    '        <p style="margin:0 0 16px;color:#7f1d1d;">请联系平台侧排查构建入口、模块产物或静态资源是否完整。</p>',
    '        <details style="margin-top:20px;text-align:left;">',
    '          <summary style="cursor:pointer;color:#991b1b;">错误详情</summary>',
    '          <pre style="margin-top:12px;padding:12px;border-radius:12px;background:#fef2f2;overflow:auto;white-space:pre-wrap;">${String(error)}</pre>',
    '        </details>',
    '      </div>',
    '    </div>',
    '  `',
    '})',
    '',
  ].join('\n')
}

/**
 * 生成诊断态轻量入口脚本文本。
 * 关键约束：
 * 1. 只触发页面模块构建校验，不挂载完整 Runtime Shell；
 * 2. 不导入 build-release-main，避免诊断阶段静态拉入 PDF、截图和布局链路；
 * 3. 必须保留预加载配置，兼容页面模块中的配置读取逻辑。
 * @param preloadedConfig Backend 下发的构建态预加载配置
 * @returns 诊断入口脚本源码
 */
export function createDiagnosticsBuildEntrySource(preloadedConfig: RuntimePreloadedConfigBundle): string {
  const serializedConfig = JSON.stringify(preloadedConfig)

  return [
    '/**',
    ' * 文件用途：诊断态构建入口，只加载 build release 页面模块映射以执行代码构建校验。',
    ' */',
    `window.__RUNTIME_PRELOADED_CONFIG__ = ${serializedConfig};`,
    "import './styles/global.css'",
    "import { BUILD_RELEASE_VIEW_MODULES } from './core/utils/build-release-view-modules'",
    "import { BUILD_DIAGNOSTICS_MODULE_LOADERS } from './core/utils/build-diagnostics-modules'",
    '',
    'const buildReleaseModuleLoaders = Object.values(BUILD_RELEASE_VIEW_MODULES)',
    'const diagnosticsModuleLoaders = [...buildReleaseModuleLoaders, ...BUILD_DIAGNOSTICS_MODULE_LOADERS]',
    'void Promise.all(diagnosticsModuleLoaders.map(async (loadModule) => loadModule())).catch((error) => {',
    "  console.error('Runtime 诊断入口加载失败', error)",
    '  throw error',
    '})',
    '',
  ].join('\n')
}

/**
 * 生成构建态 index.html。
 * @returns 构建态 index.html 源码
 */
export function createBuildIndexHtmlSource(): string {
  return [
    '<!doctype html>',
    '<html lang="zh-CN">',
    '  <head>',
    '    <meta charset="UTF-8" />',
    '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />',
    '    <title>Runtime Build</title>',
    '  </head>',
    '  <body>',
    '    <div id="app"></div>',
    '    <script type="module" src="/src/__build_entry__.ts"></script>',
    '  </body>',
    '</html>',
    '',
  ].join('\n')
}
