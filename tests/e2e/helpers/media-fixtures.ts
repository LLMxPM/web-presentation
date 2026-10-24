/** 文件功能：生成小型、确定性的 GLB 与 WAV 字节，供跨模块真实浏览器验收复用。 */

/** 按 GLB 的四字节边界填充数据块。 */
function padTo4(buffer: Buffer, padByte: number): Buffer {
  const remainder = buffer.length % 4
  return remainder === 0 ? buffer : Buffer.concat([buffer, Buffer.alloc(4 - remainder, padByte)])
}

/** 构造红色无光照三角形，便于通过像素断言模型确实渲染。 */
export function buildRedModelGlb(): Buffer {
  const positions = Buffer.alloc(9 * 4)
  const values = [0, 0.85, 0, -0.85, -0.75, 0, 0.85, -0.75, 0]
  values.forEach((value, index) => positions.writeFloatLE(value, index * 4))
  const gltf = {
    asset: { version: '2.0', generator: 'e2e-model-screenshot' },
    extensionsUsed: ['KHR_materials_unlit'],
    buffers: [{ byteLength: positions.length }],
    bufferViews: [{ buffer: 0, byteOffset: 0, byteLength: positions.length }],
    accessors: [{
      bufferView: 0,
      componentType: 5126,
      count: 3,
      type: 'VEC3',
      min: [-0.85, -0.75, 0],
      max: [0.85, 0.85, 0],
    }],
    materials: [{
      name: 'e2e-red-unlit',
      pbrMetallicRoughness: { baseColorFactor: [1, 0, 0, 1], metallicFactor: 0, roughnessFactor: 1 },
      extensions: { KHR_materials_unlit: {} },
    }],
    meshes: [{ primitives: [{ attributes: { POSITION: 0 }, material: 0 }] }],
    nodes: [{ mesh: 0 }],
    scenes: [{ nodes: [0] }],
    scene: 0,
  }
  const jsonBytes = padTo4(Buffer.from(JSON.stringify(gltf), 'utf8'), 0x20)
  const binBytes = padTo4(positions, 0x00)
  const jsonHeader = Buffer.alloc(8)
  jsonHeader.writeUInt32LE(jsonBytes.length, 0)
  jsonHeader.writeUInt32LE(0x4e4f534a, 4)
  const binHeader = Buffer.alloc(8)
  binHeader.writeUInt32LE(binBytes.length, 0)
  binHeader.writeUInt32LE(0x004e4942, 4)
  const header = Buffer.alloc(12)
  header.write('glTF', 0, 'ascii')
  header.writeUInt32LE(2, 4)
  header.writeUInt32LE(12 + 8 + jsonBytes.length + 8 + binBytes.length, 8)
  return Buffer.concat([header, jsonHeader, jsonBytes, binHeader, binBytes])
}

/** 生成浏览器可解码的单声道 PCM WAV，用于旁白与 cue 的实际播放断言。 */
export function buildToneWav(durationMs: number): Buffer {
  const sampleRate = 16_000
  const sampleCount = Math.round(sampleRate * durationMs / 1000)
  const dataLength = sampleCount * 2
  const buffer = Buffer.alloc(44 + dataLength)
  buffer.write('RIFF', 0, 'ascii')
  buffer.writeUInt32LE(36 + dataLength, 4)
  buffer.write('WAVEfmt ', 8, 'ascii')
  buffer.writeUInt32LE(16, 16)
  buffer.writeUInt16LE(1, 20)
  buffer.writeUInt16LE(1, 22)
  buffer.writeUInt32LE(sampleRate, 24)
  buffer.writeUInt32LE(sampleRate * 2, 28)
  buffer.writeUInt16LE(2, 32)
  buffer.writeUInt16LE(16, 34)
  buffer.write('data', 36, 'ascii')
  buffer.writeUInt32LE(dataLength, 40)
  for (let index = 0; index < sampleCount; index += 1) {
    const sample = Math.round(Math.sin(2 * Math.PI * 440 * index / sampleRate) * 1800)
    buffer.writeInt16LE(sample, 44 + index * 2)
  }
  return buffer
}
