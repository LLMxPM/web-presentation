/** 文件功能：使用 Backend 生成的同一真实字节夹具验证 Runtime 动作签名、stride 与内容变更。 */
// @vitest-environment node
import { afterEach, expect, it, vi } from 'vitest'
import { createHash } from 'node:crypto'
import type { GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js'
import cases from '../../../../../../../tests/fixtures/model-animation-signature-cases.json'
import { readAnimationSignatures } from './animation-signatures'
import { sha256Bytes } from './sha256-bytes'

afterEach(() => vi.unstubAllGlobals())

/** 只替换 GLTFLoader 的 bufferView 读取，保持原始 accessor 字节与索引。 */
function parserFor(json: typeof cases[number]['gltf'], binary: Buffer): GLTF['parser'] {
  return { json, async getDependency(type: string, index: number) {
    expect(type).toBe('bufferView')
    const view = json.bufferViews[index]
    return Uint8Array.from(binary.subarray(view.byteOffset, view.byteOffset + view.byteLength)).buffer
  } } as GLTF['parser']
}

it.each(cases)('$name 与 Backend 签名一致，关键帧变化使签名失效', async fixture => {
  const binary = Buffer.from(fixture.buffer_base64, 'base64')
  expect(await readAnimationSignatures(parserFor(fixture.gltf, binary))).toEqual([fixture.signature])
  const changed = Buffer.from(binary)
  changed.writeFloatLE(7, fixture.gltf.bufferViews[2].byteOffset)
  expect(await readAnimationSignatures(parserFor(fixture.gltf, changed))).not.toEqual([fixture.signature])
})

it('bufferView stride/padding 不影响相同动作的语义身份', async () => {
  const fixture = cases[0]
  const json = structuredClone(fixture.gltf)
  const binary = Buffer.from(fixture.buffer_base64, 'base64')
  const original = json.bufferViews[2]
  const output = binary.subarray(original.byteOffset, original.byteOffset + original.byteLength)
  const padded = Buffer.concat([output.subarray(0, 12), Buffer.alloc(4), output.subarray(12), Buffer.alloc(4)])
  const replacement = Buffer.concat([binary.subarray(0, original.byteOffset), padded])
  Object.assign(original, { byteStride: 16, byteLength: padded.length })
  expect(await readAnimationSignatures(parserFor(json, replacement))).toEqual([fixture.signature])
})

it('普通 HTTP 缺少 SubtleCrypto 时与 Backend 和标准 SHA-256 保持一致', async () => {
  vi.stubGlobal('crypto', {})
  for (const length of [0, 3, 55, 56, 63, 64, 65, 10000]) {
    const bytes = Uint8Array.from({ length }, (_, index) => index % 251)
    expect(await sha256Bytes(bytes)).toBe(createHash('sha256').update(bytes).digest('hex'))
  }
  for (const fixture of cases) {
    expect(await readAnimationSignatures(parserFor(fixture.gltf, Buffer.from(fixture.buffer_base64, 'base64')))).toEqual([fixture.signature])
  }
})
