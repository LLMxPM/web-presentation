/**
 * 文件功能：提供浏览器端通用 ID 生成工具，兼容缺少 crypto.randomUUID 的运行环境。
 */

const UUID_BYTE_LENGTH = 16
const UUID_HEX_RADIX = 16
const UUID_HEX_PAD_LENGTH = 2

/**
 * 生成前端临时使用的 v4 UUID。
 * @returns 标准 UUID 字符串；优先使用浏览器原生安全实现，缺失时降级生成。
 */
export function createClientUuid(): string {
  const cryptoLike = resolveCrypto()

  if (typeof cryptoLike?.randomUUID === 'function') {
    try {
      return cryptoLike.randomUUID()
    } catch {
      // 个别宿主环境可能暴露了方法但调用失败，继续走本地降级生成。
    }
  }

  const bytes = createRandomBytes(cryptoLike)
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80

  return formatUuidBytes(bytes)
}

/**
 * 读取当前全局加密对象。
 * @returns 可用的 Crypto 对象；不存在时返回 null。
 */
function resolveCrypto(): Crypto | null {
  return typeof globalThis.crypto === 'undefined' ? null : globalThis.crypto
}

/**
 * 生成 UUID 所需的 16 字节随机数据。
 * @param cryptoLike 当前环境的 Crypto 对象
 * @returns 随机字节数组
 */
function createRandomBytes(cryptoLike: Crypto | null): Uint8Array {
  const bytes = new Uint8Array(UUID_BYTE_LENGTH)

  if (typeof cryptoLike?.getRandomValues === 'function') {
    cryptoLike.getRandomValues(bytes)
    return bytes
  }

  for (let index = 0; index < bytes.length; index += 1) {
    bytes[index] = Math.floor(Math.random() * 256)
  }
  return bytes
}

/**
 * 将 UUID 字节数组格式化为带连字符的标准字符串。
 * @param bytes 已设置版本位和变体位的 16 字节数组
 */
function formatUuidBytes(bytes: Uint8Array): string {
  const hex = Array.from(bytes, byte => byte.toString(UUID_HEX_RADIX).padStart(UUID_HEX_PAD_LENGTH, '0'))
  return [
    hex.slice(0, 4).join(''),
    hex.slice(4, 6).join(''),
    hex.slice(6, 8).join(''),
    hex.slice(8, 10).join(''),
    hex.slice(10, 16).join(''),
  ].join('-')
}
