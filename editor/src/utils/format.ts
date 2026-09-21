/**
 * 文件功能：提供前端常用的时间格式化方法，统一列表页的显示风格。
 */
import { formatDateTimeInAppTimezone } from '@/utils/timezone'

/** 将接口时间按业务时区展示，缺失值统一显示占位符。 */
export function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return '-'
  }

  return formatDateTimeInAppTimezone(value)
}
