/**
 * 文件功能：提供前端常用的时间格式化方法，统一列表页的显示风格。
 */
import { formatDateTimeInAppTimezone } from '@/utils/timezone'

export function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return '-'
  }

  return formatDateTimeInAppTimezone(value)
}
