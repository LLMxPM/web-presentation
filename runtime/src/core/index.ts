/**
 * Core 模块主入口
 * 提供整个应用核心功能的统一导出
 */

// ==================== Composables ====================
// Vue 3 组合式 API 函数
export * from './composables'

// ==================== Services ====================
// 业务逻辑和数据处理服务
export * from './services'

// ==================== Types ====================
// TypeScript 类型定义
export * from './types'

// ==================== Utils ====================
// 工具函数和辅助方法
// 为了解决命名冲突，单独导出工具模块
export * as Utils from './utils'

// ==================== Router ====================
// 路由配置
export { default as createAppRouter } from './router'

// ==================== 快捷导出 ====================
// 常用功能的快捷导出，便于外部使用

// 主题系统
export { 
  useTheme
} from './composables/useTheme'

// 配置管理
export {
  initializeConfig,
  reloadAllConfigs,
  appConfig,
  appPageConfig,
  routeConfigs,
  iconConfig,
  resolveAppPageConfig,
  // 路由信息获取函数
} from './utils/config'

// 服务实例
export { pdfExportService } from './services/PDFExportService'
export { browserPrintService } from './services/BrowserPrintService'
export { pageCaptureService } from './services/PageCaptureService'
export { pptxExportService } from './services/PPTXExportService'

// 图标系统
export { iconRegistry, getIcon, hasIcon } from './utils/icon-registry'

// 事件总线
export { eventBus } from './utils/eventBus'
