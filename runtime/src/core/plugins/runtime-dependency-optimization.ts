/** 文件功能：固定浏览器预打包依赖集合，避免冷启动时生成副本独有的 Vite 依赖 URL。 */
import type { DepOptimizationOptions } from 'vite'

/**
 * 关闭运行期自动发现，使用 Vite 的显式依赖优化器生成确定的 browserHash。
 * 这些项是预打包输入，不扩大 Backend 允许导入的范围；新增 CommonJS 浏览器依赖须在此登记。
 */
export function runtimeDependencyOptimization(): DepOptimizationOptions {
  return {
    noDiscovery: true,
    include: [
      'vue', 'vue-router', '@lucide/vue', '@zumer/snapdom',
      'clsx', 'tailwind-merge', 'yaml', 'fflate', 'echarts', 'mermaid',
      'jspdf', 'pptxgenjs', 'svg-pan-zoom',
      '@mathjax/src/js/mathjax.js',
      '@mathjax/src/js/adaptors/liteAdaptor.js',
      '@mathjax/src/js/adaptors/browserAdaptor.js',
      '@mathjax/src/js/handlers/html.js',
      '@mathjax/src/js/input/tex.js',
      '@mathjax/src/js/output/svg.js',
      '@mathjax/src/js/input/tex/ams/AmsConfiguration.js',
      '@mathjax/src/js/input/tex/configmacros/ConfigMacrosConfiguration.js',
      '@mathjax/src/js/input/tex/noundefined/NoUndefinedConfiguration.js',
    ],
  }
}
