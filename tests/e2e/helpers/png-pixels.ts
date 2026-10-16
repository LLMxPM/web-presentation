/**
 * 文件功能：为 E2E 断言提供最小 PNG 解码能力，把截图产物还原成 RGBA/RGB 像素，
 * 让「模型真实可见」这类断言可以基于像素而不是仅依赖文件头。
 *
 * 只支持 Chromium 截图实际产出的 8 位无隔行真彩 PNG（colorType 2/6）；
 * 遇到其他形态直接抛错，避免静默跳过像素断言。
 */

import { inflateSync } from 'node:zlib'

/** 解码后的 PNG 像素数据（行优先，无过滤字节）。 */
export interface DecodedPng {
  width: number
  height: number
  /** 每像素通道数（RGB 为 3，RGBA 为 4）。 */
  channels: number
  pixels: Uint8Array
}

/** PNG 文件签名。 */
const PNG_SIGNATURE = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])

/**
 * 解码 PNG 字节为像素数据。
 * @param buffer PNG 文件字节
 * @returns 宽高、通道数与像素
 */
export function decodePngPixels(buffer: Buffer): DecodedPng {
  if (buffer.length < 8 || !buffer.subarray(0, 8).equals(PNG_SIGNATURE)) {
    throw new Error('PNG 文件签名不合法')
  }

  let offset = 8
  let width = 0
  let height = 0
  let bitDepth = 0
  let colorType = 0
  let interlace = 0
  const idatChunks: Buffer[] = []

  while (offset + 8 <= buffer.length) {
    const length = buffer.readUInt32BE(offset)
    const type = buffer.toString('ascii', offset + 4, offset + 8)
    const dataStart = offset + 8
    const dataEnd = dataStart + length
    if (dataEnd > buffer.length) {
      throw new Error(`PNG chunk 越界：${type}`)
    }

    if (type === 'IHDR') {
      width = buffer.readUInt32BE(dataStart)
      height = buffer.readUInt32BE(dataStart + 4)
      bitDepth = buffer[dataStart + 8]
      colorType = buffer[dataStart + 9]
      interlace = buffer[dataStart + 12]
    } else if (type === 'IDAT') {
      idatChunks.push(buffer.subarray(dataStart, dataEnd))
    } else if (type === 'IEND') {
      break
    }

    offset = dataEnd + 4
  }

  if (width <= 0 || height <= 0) {
    throw new Error('PNG 缺少有效 IHDR')
  }
  if (bitDepth !== 8 || (colorType !== 2 && colorType !== 6) || interlace !== 0) {
    throw new Error(`不支持的 PNG 形态：bitDepth=${bitDepth} colorType=${colorType} interlace=${interlace}`)
  }

  const channels = colorType === 6 ? 4 : 3
  const stride = width * channels
  const inflated = inflateSync(Buffer.concat(idatChunks))
  if (inflated.length < (stride + 1) * height) {
    throw new Error('PNG 像素数据长度不足')
  }

  const pixels = new Uint8Array(stride * height)
  let rawOffset = 0
  let previousRow = new Uint8Array(stride)

  for (let y = 0; y < height; y += 1) {
    const filter = inflated[rawOffset]
    rawOffset += 1
    const row = new Uint8Array(inflated.subarray(rawOffset, rawOffset + stride))
    rawOffset += stride
    unfilterScanline(row, previousRow, channels, filter)
    pixels.set(row, y * stride)
    previousRow = row
  }

  return { width, height, channels, pixels }
}

/**
 * 按 PNG 过滤器类型还原一行像素（原地修改）。
 * @param row 当前行原始字节
 * @param previousRow 上一行还原后的字节
 * @param channels 每像素通道数
 * @param filter 过滤器类型
 */
function unfilterScanline(row: Uint8Array, previousRow: Uint8Array, channels: number, filter: number): void {
  const stride = row.length
  for (let index = 0; index < stride; index += 1) {
    const left = index >= channels ? row[index - channels] : 0
    const up = previousRow[index]
    const upLeft = index >= channels ? previousRow[index - channels] : 0
    let value = row[index]

    switch (filter) {
      case 0:
        break
      case 1:
        value = (value + left) & 0xff
        break
      case 2:
        value = (value + up) & 0xff
        break
      case 3:
        value = (value + ((left + up) >> 1)) & 0xff
        break
      case 4: {
        const estimate = left + up - upLeft
        const distanceLeft = Math.abs(estimate - left)
        const distanceUp = Math.abs(estimate - up)
        const distanceUpLeft = Math.abs(estimate - upLeft)
        const predictor = distanceLeft <= distanceUp && distanceLeft <= distanceUpLeft
          ? left
          : (distanceUp <= distanceUpLeft ? up : upLeft)
        value = (value + predictor) & 0xff
        break
      }
      default:
        throw new Error(`不支持的 PNG 行过滤器：${filter}`)
    }

    row[index] = value
  }
}

/**
 * 统计满足条件的像素数量。
 * @param decoded 解码结果
 * @param predicate 像素判断函数（r/g/b 为 0..255）
 * @returns 命中像素数
 */
export function countPixels(
  decoded: DecodedPng,
  predicate: (red: number, green: number, blue: number) => boolean,
): number {
  const { pixels, channels } = decoded
  let count = 0
  for (let index = 0; index < pixels.length; index += channels) {
    if (predicate(pixels[index], pixels[index + 1], pixels[index + 2])) {
      count += 1
    }
  }
  return count
}

/**
 * 统计明显偏红的像素数量；用于验证三维模型（红色基色材质）确实出现在截图里。
 * 背景白/灰、文本黑都不会命中。
 * @param decoded 解码结果
 * @returns 命中的红色系像素数
 */
export function countStrongRedPixels(decoded: DecodedPng): number {
  return countPixels(decoded, (red, green, blue) => {
    return red - green > 40 && red - blue > 40 && red > 120
  })
}
