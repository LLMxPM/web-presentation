/** 文件功能：隔离项目界面偏好的存储，存储不可用时仍能正常浏览。 */
import { getRuntimePreviewContext } from './path'

/** 构建按项目隔离的偏好键；独立构建以文档路径区分。 */
export function runtimePreferenceKey(name: string): string {
  const context = getRuntimePreviewContext()
  const scope = context?.projectId || `${location.origin}${location.pathname}`
  return `runtime:${scope}:${name}`
}

/** 读取偏好；隐私模式或非法存储统一采用默认值。 */
export function readRuntimePreference(name: string, fallback: string): string {
  try { return localStorage.getItem(runtimePreferenceKey(name)) ?? fallback } catch { return fallback }
}

/** 保存当前项目的偏好，失败不影响页面导航。 */
export function writeRuntimePreference(name: string, value: string): void {
  try { localStorage.setItem(runtimePreferenceKey(name), value) } catch { /* 浏览器可禁用存储。 */ }
}
