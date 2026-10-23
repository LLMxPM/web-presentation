// 文件功能：生成 G1 验收所需的真实素材——带骨骼片段的 GLB 与有声 WAV。
import { Buffer } from 'node:buffer'

/** 组装标准 GLB 容器：12 字节头 + JSON 块 + BIN 块，均按 4 字节对齐。 */
function packGlb(json, bin) {
  const jsonBytes = Buffer.from(JSON.stringify(json), 'utf8')
  const jsonChunk = Buffer.concat([jsonBytes, Buffer.alloc((4 - (jsonBytes.length % 4)) % 4, 0x20)])
  const binChunk = Buffer.concat([bin, Buffer.alloc((4 - (bin.length % 4)) % 4, 0)])
  const total = 12 + 8 + jsonChunk.length + 8 + binChunk.length
  const header = Buffer.alloc(12)
  header.writeUInt32LE(0x46546c67, 0)
  header.writeUInt32LE(2, 4)
  header.writeUInt32LE(total, 8)
  const jsonHeader = Buffer.alloc(8)
  jsonHeader.writeUInt32LE(jsonChunk.length, 0)
  jsonHeader.writeUInt32LE(0x4e4f534a, 4)
  const binHeader = Buffer.alloc(8)
  binHeader.writeUInt32LE(binChunk.length, 0)
  binHeader.writeUInt32LE(0x004e4942, 4)
  return Buffer.concat([header, jsonHeader, jsonChunk, binHeader, binChunk])
}

/**
 * 生成两秒、绕 Y 轴旋转 90° 的三角形 GLB。
 * 动作输出为真实 LINEAR 采样，供 GLTFLoader 与 AnimationMixer 实际解析。
 */
export function buildSpinGlb() {
  const positions = [-1, -1, 0, 1, -1, 0, 0, 1, 0]
  const normals = [0, 0, 1, 0, 0, 1, 0, 0, 1]
  const times = [0, 2]
  const quaternions = [0, 0, 0, 1, 0, Math.SQRT1_2, 0, Math.SQRT1_2]
  const bin = Buffer.alloc(112)
  positions.forEach((value, index) => bin.writeFloatLE(value, index * 4))
  normals.forEach((value, index) => bin.writeFloatLE(value, 36 + index * 4))
  times.forEach((value, index) => bin.writeFloatLE(value, 72 + index * 4))
  quaternions.forEach((value, index) => bin.writeFloatLE(value, 80 + index * 4))

  const json = {
    asset: { version: '2.0', generator: 'web-presentation-motion-g1' },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{ mesh: 0, rotation: [0, 0, 0, 1] }],
    materials: [{ pbrMetallicRoughness: { baseColorFactor: [0.9, 0.45, 0.2, 1], metallicFactor: 0, roughnessFactor: 0.85 } }],
    meshes: [{ primitives: [{ attributes: { POSITION: 0, NORMAL: 1 }, material: 0, mode: 4 }] }],
    buffers: [{ byteLength: 112 }],
    bufferViews: [
      { buffer: 0, byteOffset: 0, byteLength: 36, target: 34962 },
      { buffer: 0, byteOffset: 36, byteLength: 36, target: 34962 },
      { buffer: 0, byteOffset: 72, byteLength: 8 },
      { buffer: 0, byteOffset: 80, byteLength: 32 },
    ],
    accessors: [
      { bufferView: 0, componentType: 5126, count: 3, type: 'VEC3', min: [-1, -1, 0], max: [1, 1, 0] },
      { bufferView: 1, componentType: 5126, count: 3, type: 'VEC3' },
      { bufferView: 2, componentType: 5126, count: 2, type: 'SCALAR', min: [0], max: [2] },
      { bufferView: 3, componentType: 5126, count: 2, type: 'VEC4' },
    ],
    animations: [{
      name: 'Spin',
      channels: [{ sampler: 0, target: { node: 0, path: 'rotation' } }],
      samplers: [{ input: 2, output: 3, interpolation: 'LINEAR' }],
    }],
  }
  return packGlb(json, bin)
}

/** 生成 2 秒 440Hz 单声道 16bit WAV；用于真实触发浏览器自动播放策略。 */
export function buildToneWav({ seconds = 2, sampleRate = 44100, frequency = 440, amplitude = 0.25 } = {}) {
  const sampleCount = Math.floor(seconds * sampleRate)
  const data = Buffer.alloc(sampleCount * 2)
  for (let index = 0; index < sampleCount; index += 1) {
    const time = index / sampleRate
    const envelope = Math.max(0, Math.min(1, time / 0.05, (seconds - time) / 0.05))
    const value = Math.sin(2 * Math.PI * frequency * time) * amplitude * envelope
    data.writeInt16LE(Math.round(value * 32767), index * 2)
  }
  const header = Buffer.alloc(44)
  header.write('RIFF', 0)
  header.writeUInt32LE(36 + data.length, 4)
  header.write('WAVE', 8)
  header.write('fmt ', 12)
  header.writeUInt32LE(16, 16)
  header.writeUInt16LE(1, 20)
  header.writeUInt16LE(1, 22)
  header.writeUInt32LE(sampleRate, 24)
  header.writeUInt32LE(sampleRate * 2, 28)
  header.writeUInt16LE(2, 32)
  header.writeUInt16LE(16, 34)
  header.write('data', 36)
  header.writeUInt32LE(data.length, 40)
  return Buffer.concat([header, data])
}
