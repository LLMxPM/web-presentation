/**
 * 文件用途：定义可视化编辑批量改写过程的稳定错误类型。
 */

export class VisualEditApplyError extends Error {
  statusCode: number
  code: string

  constructor(statusCode: number, code: string, message: string, cause?: unknown) {
    super(message, { cause })
    this.name = 'VisualEditApplyError'
    this.statusCode = statusCode
    this.code = code
  }
}
