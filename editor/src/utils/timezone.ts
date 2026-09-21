/**
 * 文件功能：封装前端业务时区读取、时间展示与日期片段生成工具，避免浏览器本地时区造成语义漂移。
 */

const DEFAULT_APP_TIMEZONE = 'Asia/Shanghai'

export let APP_TIMEZONE = import.meta.env.VITE_APP_TIMEZONE?.trim() || DEFAULT_APP_TIMEZONE

/** 挂载应用前设置后端业务时区；先校验名称，非法配置不覆盖已有值。 */
export function setAppTimezone(timezone: string): void {
  const normalized = timezone.trim()
  new Intl.DateTimeFormat('zh-CN', { timeZone: normalized }).format(0)
  APP_TIMEZONE = normalized
}

/** 解析接口时间；历史无时区日期时间直接补 UTC，已有偏移保持原有时间点。 */
export function parseApiDate(value: string | number | Date): Date {
  if (value instanceof Date) return value
  if (typeof value !== 'string') return new Date(value)
  const normalized = value.trim()
  const isNaiveDateTime = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(normalized)
  return new Date(isNaiveDateTime ? `${normalized.replace(' ', 'T')}Z` : normalized)
}

/**
 * 按业务时区格式化时间，统一前端列表和详情页的时间展示。
 * @param value 原始时间值
 * @returns 业务时区下的短日期时间文本
 */
export function formatDateTimeInAppTimezone(value: string | number | Date) {
  const date = parseApiDate(value)
  if (Number.isNaN(date.getTime())) return '-'
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'short',
    timeStyle: 'short',
    timeZone: APP_TIMEZONE,
  }).format(date)
}

/**
 * 生成业务时区下的 yyyy-mm-dd 日期片段，用于 Runtime 预览目录命名。
 * @param value 原始时间值，默认取当前时间
 * @returns 业务时区日期片段
 */
export function getAppDateSegment(value: string | number | Date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone: APP_TIMEZONE,
  }).formatToParts(parseApiDate(value))

  const year = parts.find(part => part.type === 'year')?.value ?? ''
  const month = parts.find(part => part.type === 'month')?.value ?? ''
  const day = parts.find(part => part.type === 'day')?.value ?? ''
  return `${year}-${month}-${day}`
}
