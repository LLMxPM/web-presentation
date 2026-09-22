/**
 * 文件系统和下载相关工具函数
 */

/**
 * 生成文件名
 * @param customName 自定义文件名
 * @param nameTemplate 文件名模板，默认'export-{timestamp}'
 * @param includeTimestamp 是否包含时间戳
 * @param extension 文件扩展名，默认'.pdf'
 * @param now 生成时间，默认使用当前用户本地时间
 * @returns 生成的文件名
 */
export function generateFilename(
  customName?: string,
  nameTemplate: string = 'export-{timestamp}',
  includeTimestamp: boolean = true,
  extension: string = '.pdf',
  now: Date = new Date()
): string {
  if (customName) {
    return customName.endsWith(extension) ? customName : `${customName}${extension}`
  }

  const timestamp = includeTimestamp ? formatLocalFilenameTimestamp(now) : ''
  let filename = nameTemplate
    .replace('{timestamp}', timestamp)
    .replace(/\s+-\s*$/g, '')
    .replace(/[-_\s]+$/g, '')

  filename = sanitizeFilenameBase(filename || 'export') || 'export'

  return filename.endsWith(extension) ? filename : `${filename}${extension}`
}

/**
 * 按用户本地时区格式化适合文件名使用的时间。
 * @param date 时间对象
 * @returns YYYY-MM-DD_HH-mm-ss 格式字符串
 */
export function formatLocalFilenameTimestamp(date: Date = new Date()): string {
  const pad = (value: number) => String(value).padStart(2, '0')

  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
  ].join('-') + '_' + [
    pad(date.getHours()),
    pad(date.getMinutes()),
    pad(date.getSeconds()),
  ].join('-')
}

/**
 * 清理默认文件名中的非法字符，保留中文与常规可读字符。
 * @param filenameBase 不含扩展名的文件名
 * @returns 安全文件名主体
 */
export function sanitizeFilenameBase(filenameBase: string): string {
  return filenameBase
    // eslint-disable-next-line no-control-regex
    .replace(/[<>:"/\\|?*\u0000-\u001F]/g, '-')
    .replace(/\s+/g, ' ')
    .replace(/-+/g, '-')
    .replace(/^[\s.-]+|[\s.-]+$/g, '')
}

/**
 * 下载文件
 * @param blob 文件数据
 * @param filename 文件名
 */
export function downloadFile(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/**
 * 将Canvas转换为Blob
 * @param canvas Canvas元素
 * @param quality 图片质量(0-1)
 * @param type 图片类型
 * @returns Promise<Blob>
 */
export function canvasToBlob(
  canvas: HTMLCanvasElement,
  quality: number = 0.9,
  type: string = 'image/jpeg'
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob) {
          resolve(blob)
        } else {
          reject(new Error('Canvas转换为Blob失败'))
        }
      },
      type,
      quality
    )
  })
}

/**
 * 优化Canvas质量
 * @param canvas 原始canvas
 * @param quality 质量参数(0-1)
 * @returns 优化后的canvas
 */
export function optimizeCanvas(canvas: HTMLCanvasElement, quality: number = 0.9): HTMLCanvasElement {
  if (quality >= 1) {
    return canvas
  }
  
  const optimizedCanvas = document.createElement('canvas')
  const ctx = optimizedCanvas.getContext('2d')
  
  if (!ctx) {
    return canvas
  }
  
  // 根据质量调整尺寸
  const scale = Math.sqrt(quality)
  optimizedCanvas.width = canvas.width * scale
  optimizedCanvas.height = canvas.height * scale
  
  // 启用图像平滑
  ctx.imageSmoothingEnabled = true
  ctx.imageSmoothingQuality = 'high'
  
  // 绘制优化后的图像
  ctx.drawImage(canvas, 0, 0, optimizedCanvas.width, optimizedCanvas.height)
  
  return optimizedCanvas
}
