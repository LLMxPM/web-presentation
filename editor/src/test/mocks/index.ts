/**
 * 文件功能：提供 Editor 测试中常用的轻量 mock 构造工具。
 */
import { vi, type Mock } from 'vitest'

/**
 * 创建一个默认返回 Promise 的 mock 函数，便于 API 层测试统一复用。
 * @param value 默认 resolve 的值
 * @returns Vitest mock 函数
 */
export function createResolvedMock<T>(value: T): Mock<() => Promise<T>> {
  return vi.fn<() => Promise<T>>().mockResolvedValue(value as Awaited<T>)
}
