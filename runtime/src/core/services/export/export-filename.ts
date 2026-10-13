/**
 * 文件用途：解析导出文件名与页面标题，供 PDF、PPTX 与浏览器打印服务共用。
 *
 * 与任务生命周期无关：这里只做「从 Router、应用配置和当前文档标题推导出文件名」的纯计算，
 * 不持有任何运行态，因此可以在 beginTask 之前安全调用。
 */

import type { Router } from 'vue-router'
import type { ExportMode } from '@/core/types/export-common'
import { appConfig as runtimeAppConfig } from '@/core/utils/config'
import { generateFilename } from '@/core/utils/file'

/**
 * 规范化标题文本，空串与纯空白不作为有效标题。
 * @param title 候选标题，可能来自路由 meta 或 document.title
 * @returns 裁剪后的标题，无效时返回 undefined
 */
export function pickExportTitle(title: unknown): string | undefined {
  if (typeof title !== 'string') {
    return undefined
  }

  const normalized = title.trim()
  return normalized.length > 0 ? normalized : undefined
}

/**
 * 解析当前页面标题。
 * 回退顺序固定为路由 meta.title → document.title → 项目标题 → '页面'，保证任何环境下都有可用值。
 * @param router 当前路由器，未注入时为 null
 * @returns 当前页面标题
 */
export function resolveCurrentPageTitle(router: Router | null): string {
  const routeTitle = pickExportTitle(router?.currentRoute.value.meta?.title)
  const documentTitle = typeof document === 'undefined' ? undefined : pickExportTitle(document.title)
  return routeTitle ?? documentTitle ?? pickExportTitle(runtimeAppConfig.value.app.title) ?? '页面'
}

/**
 * 解析默认文件名主体：导出全部页面时用项目标题，导出单页时用当前页标题。
 * @param mode 导出范围
 * @param router 当前路由器
 * @returns 不含时间戳与扩展名的文件名主体
 */
export function resolveDefaultFilenameBase(mode: ExportMode, router: Router | null): string {
  if (mode === 'all') {
    return pickExportTitle(runtimeAppConfig.value.app.title) ?? '项目'
  }

  return resolveCurrentPageTitle(router)
}

/**
 * 生成带时间戳与扩展名的导出文件名。
 * @param mode 导出范围
 * @param router 当前路由器
 * @param fileExtension 文件扩展名，必须带前导点，如 '.pdf' / '.pptx'
 * @param customFilename 用户自定义文件名，非空时只补扩展名
 * @returns 最终文件名
 */
export function resolveExportFilename(
  mode: ExportMode,
  router: Router | null,
  fileExtension: string,
  customFilename?: string,
): string {
  const baseName = resolveDefaultFilenameBase(mode, router)
  return generateFilename(customFilename, `${baseName}-{timestamp}`, true, fileExtension)
}
