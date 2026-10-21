// 文件功能：生成 WP01 自有短音频、带骨骼动作的自包含 GLB 及明确反例，不下载外部素材。
import { mkdir, writeFile, readFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

/** 创建四秒低幅提示音作为可重现旁白时钟替身；不含语音，采样率 48kHz。 */
function makeWav() {
  const count = 48000 * 4
  const bytes = Buffer.alloc(44 + count * 2)
  bytes.write('RIFF'); bytes.writeUInt32LE(bytes.length - 8, 4); bytes.write('WAVEfmt ', 8)
  bytes.writeUInt32LE(16, 16); bytes.writeUInt16LE(1, 20); bytes.writeUInt16LE(1, 22)
  bytes.writeUInt32LE(48000, 24); bytes.writeUInt32LE(96000, 28)
  bytes.writeUInt16LE(2, 32); bytes.writeUInt16LE(16, 34)
  bytes.write('data', 36); bytes.writeUInt32LE(count * 2, 40)
  for (let i = 0; i < count; i++) bytes.writeInt16LE(Math.round(Math.sin(i / 48000 * 440 * Math.PI * 2) * 600), 44 + i * 2)
  return bytes
}

/** 输出一个关节控制三角形的合法 GLB；动作控制骨骼旋转，不能用普通节点旋转冒充蒙皮隔离。 */
function makeGlb(mode) {
  const chunks = [], views = [], accessors = []
  let length = 0
  /** 添加对齐的 bufferView 与 accessor，保存 glTF 所需边界。 */
  function add(array, type, componentType, count, bounds = {}) {
    const bytes = Buffer.from(array.buffer, array.byteOffset, array.byteLength)
    const padding = Buffer.alloc((4 - bytes.length % 4) % 4)
    const view = views.push({ buffer: 0, byteOffset: length, byteLength: bytes.length }) - 1
    chunks.push(bytes, padding); length += bytes.length + padding.length
    return accessors.push({ bufferView: view, componentType, count, type, ...bounds }) - 1
  }
  const position = add(new Float32Array([-0.7, 0, 0, 0.7, 0, 0, 0, 1.3, 0]), 'VEC3', 5126, 3, { min: [-0.7, 0, 0], max: [0.7, 1.3, 0] })
  const normal = add(new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]), 'VEC3', 5126, 3)
  const joints = add(new Uint16Array(12), 'VEC4', 5123, 3)
  const weights = add(new Float32Array([1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]), 'VEC4', 5126, 3)
  const inverse = add(new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]), 'MAT4', 5126, 1)
  const times = add(new Float32Array([0, 1, 2]), 'SCALAR', 5126, 3, { min: [0], max: [2] })
  const rotations = add(new Float32Array([0, 0, 0, 1, 0, 0, Math.sin(Math.PI / 4), Math.cos(Math.PI / 4), 0, 0, 0, 1]), 'VEC4', 5126, 3)
  const clip = { name: 'wave', samplers: [{ input: times, output: rotations, interpolation: 'LINEAR' }], channels: [{ sampler: 0, target: { node: 1, path: 'rotation' } }] }
  const gltf = {
    asset: { version: '2.0', generator: 'web-presentation WP01 own fixture' }, scene: 0,
    scenes: [{ nodes: [0] }], nodes: [{ name: 'root', children: [1, 2] }, { name: 'joint' }, { name: 'triangle', mesh: 0, skin: 0 }],
    skins: [{ joints: [1], inverseBindMatrices: inverse, skeleton: 1 }],
    meshes: [{ primitives: [{ attributes: { POSITION: position, NORMAL: normal, JOINTS_0: joints, WEIGHTS_0: weights }, material: 0 }] }],
    materials: [{ doubleSided: true, pbrMetallicRoughness: { baseColorFactor: [0.2, 0.7, 1, 1], metallicFactor: 0, roughnessFactor: 1 } }],
    buffers: [{ byteLength: length }], bufferViews: views, accessors,
    animations: mode === 'none' ? [] : mode === 'duplicate' ? [clip, structuredClone(clip)] : mode === 'missing' ? [{ ...clip, channels: [{ sampler: 0, target: { node: 99, path: 'rotation' } }] }] : [clip],
  }
  let json = Buffer.from(JSON.stringify(gltf))
  json = Buffer.concat([json, Buffer.alloc((4 - json.length % 4) % 4, 32)])
  const header = Buffer.alloc(20), binHeader = Buffer.alloc(8)
  header.writeUInt32LE(0x46546c67); header.writeUInt32LE(2, 4); header.writeUInt32LE(28 + json.length + length, 8)
  header.writeUInt32LE(json.length, 12); header.writeUInt32LE(0x4e4f534a, 16)
  binHeader.writeUInt32LE(length); binHeader.writeUInt32LE(0x004e4942, 4)
  return Buffer.concat([header, json, binHeader, ...chunks])
}

/** 生成全部静态样本；视频由受控浏览器编码，随后一并计算文件身份。 */
export async function generateFixtures(directory) {
  await mkdir(directory, { recursive: true })
  const wav = makeWav()
  if (process.platform === 'win32') {
    const speechPath = `${directory}/speech-source.wav`
    execFileSync('powershell.exe', ['-NoProfile', '-File', fileURLToPath(new URL('./narration.ps1', import.meta.url)), '-Output', speechPath, '-Text', '标题与模型，同步播放。'], { windowsHide: true })
    const speech = await readFile(speechPath)
    let offset = 12, payload
    while (offset + 8 <= speech.length) {
      const size = speech.readUInt32LE(offset + 4)
      if (speech.toString('ascii', offset, offset + 4) === 'data') { payload = speech.subarray(offset + 8, offset + 8 + size); break }
      offset += 8 + size + size % 2
    }
    if (!payload || payload.length > wav.length - 44) throw new Error('旁白必须在四秒内；不能截断语音充当合法样本')
    wav.fill(0, 44); payload.copy(wav, 44)
  }
  await writeFile(`${directory}/voice.wav`, wav)
  for (const mode of ['animated', 'none', 'duplicate', 'missing']) await writeFile(`${directory}/${mode}.glb`, makeGlb(mode))
}

/** 汇总实物 hash 与来源；不把票据 URL 记录为资产身份。 */
export async function fixtureManifest(directory) {
  return Promise.all(['voice.wav', 'clock.webm', 'animated.glb', 'none.glb', 'duplicate.glb', 'missing.glb'].map(async name => {
    const data = await readFile(`${directory}/${name}`)
    return { name, bytes: data.length, sha256: createHash('sha256').update(data).digest('hex'), source: '本仓脚本原创生成；可随本仓 AGPL-3.0-or-later 分发', generator: 'tests/experiments/motion-wp01/fixtures.mjs + encode-video.mjs' }
  }))
}
