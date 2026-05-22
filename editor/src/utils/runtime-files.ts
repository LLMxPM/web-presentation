/**
 * 文件功能：提供 Runtime 预览文件上传相关的路径拼装工具，统一生成符合 Runtime 白名单约束的目标目录。
 */

/**
 * 构建页面预览上传目录。
 * @param userId 当前用户标识
 * @param dateSegment 日期片段，格式通常为 yyyy-mm-dd
 * @returns 可写入 Runtime 白名单目录的相对路径
 */
export function buildRuntimePreviewTargetPath(userId: string | number, dateSegment: string): string {
  const normalizedUserId = String(userId || 'anonymous').trim() || 'anonymous'
  const normalizedDateSegment = String(dateSegment || '').trim()
  return `src/views/${normalizedDateSegment}/${normalizedUserId}`
}
