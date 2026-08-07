/**
 * 文件功能：提供统一的剪贴板写入与结果提示。
 */
import { Message } from '@/utils/message'

/**
 * 把文本写入剪贴板并提示结果。
 * @param text 待写入文本
 * @param successMessage 写入成功后的提示文案
 */
export async function copyTextToClipboard(text: string, successMessage: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
    Message.success(successMessage)
  } catch {
    Message.error('复制失败，请检查浏览器剪贴板权限。')
  }
}
