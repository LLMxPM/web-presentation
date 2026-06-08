// 文件功能：封装页面截图下载 URL、文件名与浏览器下载触发逻辑，供详情页和页面列表复用。

/**
 * 使用后端下载参数触发浏览器下载，避免前端跨域读取对象存储图片。
 * @param screenshotUrl 页面截图访问地址
 * @param pageTitle 页面标题
 * @param versionNo 截图对应的页面版本号
 */
export function downloadPageScreenshot(screenshotUrl: string, pageTitle: string, versionNo: number | null): void {
  triggerBrowserDownload(
    buildScreenshotDownloadUrl(screenshotUrl),
    buildScreenshotDownloadFilename(pageTitle, screenshotUrl, versionNo),
  )
}

/**
 * 创建临时 a 标签，让浏览器按响应头处理下载。
 * @param downloadUrl 带下载参数的截图地址
 * @param filename 浏览器保存时建议使用的文件名
 */
export function triggerBrowserDownload(downloadUrl: string, filename: string): void {
  const link = document.createElement('a')
  link.href = downloadUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
}

/**
 * 在原截图地址上追加 download=1，保留版本参数用于缓存命中。
 * @param screenshotUrl 页面截图访问地址
 */
export function buildScreenshotDownloadUrl(screenshotUrl: string): string {
  try {
    const parsedUrl = new URL(screenshotUrl, window.location.origin)
    parsedUrl.searchParams.set('download', '1')
    return parsedUrl.toString()
  } catch {
    const separator = screenshotUrl.includes('?') ? '&' : '?'
    return `${screenshotUrl}${separator}download=1`
  }
}

/**
 * 为截图下载生成稳定文件名，保留页面标题并补充版本号。
 * @param pageTitle 页面标题
 * @param screenshotUrl 页面截图访问地址
 * @param versionNo 截图对应的页面版本号
 */
export function buildScreenshotDownloadFilename(
  pageTitle: string,
  screenshotUrl: string | null,
  versionNo: number | null,
): string {
  const safeTitle = pageTitle.trim().replace(/[\\/:*?"<>|]+/g, '-').replace(/\s+/g, '-').slice(0, 64) || 'page-screenshot'
  const versionSuffix = versionNo ? `-v${versionNo}` : ''
  return `${safeTitle}${versionSuffix}.${resolveScreenshotExtension(screenshotUrl)}`
}

/**
 * 从截图地址推断下载扩展名，无法识别时默认使用 png。
 * @param screenshotUrl 页面截图访问地址
 */
function resolveScreenshotExtension(screenshotUrl: string | null): string {
  if (!screenshotUrl) return 'png'

  try {
    const parsedUrl = new URL(screenshotUrl, window.location.origin)
    const extension = parsedUrl.pathname.match(/\.([a-z0-9]+)$/i)?.[1]?.toLowerCase()
    if (extension && ['png', 'jpg', 'jpeg', 'webp'].includes(extension)) {
      return extension === 'jpeg' ? 'jpg' : extension
    }
  } catch {
    return 'png'
  }

  return 'png'
}
