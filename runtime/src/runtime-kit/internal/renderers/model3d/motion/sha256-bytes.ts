/** 文件功能：为动作内容身份计算 SHA-256，兼容未提供 SubtleCrypto 的 HTTP 预览环境。 */
const ROUND_CONSTANTS = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
])

/** 32 位循环右移；所有运算最终通过 Uint32Array 截断为无符号整型。 */
function rotate(value: number, bits: number): number { return (value >>> bits) | (value << (32 - bits)) }

/** 按 SHA-256 分组填充和压缩；仅供内容指纹，不承担签名或密钥操作。 */
function fallback(bytes: Uint8Array): Uint8Array {
  const padded = new Uint8Array(Math.ceil((bytes.length + 9) / 64) * 64)
  padded.set(bytes)
  padded[bytes.length] = 0x80
  const view = new DataView(padded.buffer)
  view.setUint32(padded.length - 8, Math.floor(bytes.length / 0x20000000))
  view.setUint32(padded.length - 4, (bytes.length * 8) >>> 0)
  const state = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19])
  const words = new Uint32Array(64)
  for (let block = 0; block < padded.length; block += 64) {
    for (let i = 0; i < 16; i++) words[i] = view.getUint32(block + i * 4)
    for (let i = 16; i < 64; i++) {
      const left = words[i - 15], right = words[i - 2]
      const s0 = rotate(left, 7) ^ rotate(left, 18) ^ (left >>> 3)
      const s1 = rotate(right, 17) ^ rotate(right, 19) ^ (right >>> 10)
      words[i] = words[i - 16] + s0 + words[i - 7] + s1
    }
    let [a, b, c, d, e, f, g, h] = state
    for (let i = 0; i < 64; i++) {
      const s1 = rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25)
      const choice = (e & f) ^ (~e & g)
      const t1 = (h + s1 + choice + ROUND_CONSTANTS[i] + words[i]) >>> 0
      const s0 = rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22)
      const majority = (a & b) ^ (a & c) ^ (b & c)
      const t2 = (s0 + majority) >>> 0
      h = g; g = f; f = e; e = (d + t1) >>> 0
      d = c; c = b; b = a; a = (t1 + t2) >>> 0
    }
    for (const [i, value] of [a, b, c, d, e, f, g, h].entries()) state[i] += value
  }
  const digest = new Uint8Array(32)
  const output = new DataView(digest.buffer)
  state.forEach((word, index) => output.setUint32(index * 4, word))
  return digest
}

/** 优先使用平台实现；HTTP 非安全上下文缺少 subtle 时保持同一内容身份。 */
export async function sha256Bytes(bytes: Uint8Array<ArrayBuffer>): Promise<string> {
  const digest = globalThis.crypto?.subtle
    ? new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256', bytes))
    : fallback(bytes)
  return Array.from(digest, value => value.toString(16).padStart(2, '0')).join('')
}
