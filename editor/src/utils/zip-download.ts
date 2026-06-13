/**
 * 文件功能：提供浏览器端 Blob 下载触发工具，供资源、样式和组件离线包保存复用。
 */

/**
 * 触发浏览器下载指定 Blob。
 * @param blob 下载内容。
 * @param filename 浏览器保存文件名。
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const downloadUrl = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = downloadUrl
  link.download = filename
  link.click()
  window.URL.revokeObjectURL(downloadUrl)
}
