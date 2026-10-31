/** 文件功能：生成小型、确定性的 GLB 与 WAV 字节，供跨模块真实浏览器验收复用。 */

/** 按 GLB 的四字节边界填充数据块。 */
function padTo4(buffer: Buffer, padByte: number): Buffer {
  const remainder = buffer.length % 4
  return remainder === 0 ? buffer : Buffer.concat([buffer, Buffer.alloc(4 - remainder, padByte)])
}

/** 构造红色无光照三角形；蒙皮版本放大十倍，用于捕获按骨骼位置取景导致的裁切。 */
export function buildRedModelGlb({ skinned = false }: { skinned?: boolean } = {}): Buffer {
  const positions = Buffer.alloc(9 * 4)
  const values = [0, 0.85, 0, -0.85, -0.75, 0, 0.85, -0.75, 0]
  const scale = skinned ? 10 : 1
  values.forEach((value, index) => positions.writeFloatLE(value * scale, index * 4))
  const joints = Buffer.alloc(12)
  const weights = Buffer.alloc(48)
  for (let index = 0; index < 3; index += 1) weights.writeFloatLE(1, index * 16)
  const binary = skinned ? Buffer.concat([positions, joints, weights]) : positions
  const gltf = {
    asset: { version: '2.0', generator: 'e2e-model-screenshot' },
    extensionsUsed: ['KHR_materials_unlit'],
    buffers: [{ byteLength: binary.length }],
    bufferViews: [
      { buffer: 0, byteOffset: 0, byteLength: positions.length },
      ...(skinned ? [
        { buffer: 0, byteOffset: 36, byteLength: joints.length },
        { buffer: 0, byteOffset: 48, byteLength: weights.length },
      ] : []),
    ],
    accessors: [{
      bufferView: 0,
      componentType: 5126,
      count: 3,
      type: 'VEC3',
      min: [-0.85 * scale, -0.75 * scale, 0],
      max: [0.85 * scale, 0.85 * scale, 0],
    }, ...(skinned ? [
      { bufferView: 1, componentType: 5121, count: 3, type: 'VEC4' },
      { bufferView: 2, componentType: 5126, count: 3, type: 'VEC4' },
    ] : [])],
    materials: [{
      name: 'e2e-red-unlit',
      pbrMetallicRoughness: { baseColorFactor: [1, 0, 0, 1], metallicFactor: 0, roughnessFactor: 1 },
      extensions: { KHR_materials_unlit: {} },
    }],
    meshes: [{ primitives: [{ attributes: skinned ? { POSITION: 0, JOINTS_0: 1, WEIGHTS_0: 2 } : { POSITION: 0 }, material: 0 }] }],
    nodes: skinned ? [{ mesh: 0, skin: 0 }, { name: 'joint' }] : [{ mesh: 0 }],
    ...(skinned ? { skins: [{ joints: [1] }] } : {}),
    scenes: [{ nodes: skinned ? [0, 1] : [0] }],
    scene: 0,
  }
  const jsonBytes = padTo4(Buffer.from(JSON.stringify(gltf), 'utf8'), 0x20)
  const binBytes = padTo4(binary, 0x00)
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
