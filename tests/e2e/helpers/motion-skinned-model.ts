/**
 * 文件功能：生成真正使用 glTF skin/joint 的最小动作 GLB，供远程骨骼捕获验收。
 */

/** 将 GLB 块填充到四字节边界。 */
function pad4(bytes: Buffer, value: number): Buffer {
  const pad = (4 - bytes.length % 4) % 4
  return pad ? Buffer.concat([bytes, Buffer.alloc(pad, value)]) : bytes
}

/**
 * 构造无光照红色三角网格，三个顶点均由一个实际 joint 驱动；BoneSlide 把 joint 平移 0.8 单位。
 * 顶点权重与 inverse bind matrix 都写入标准 GLB，避免把普通节点变换误当作骨骼测试。
 */
export function buildSkinnedMotionGlb(translationEndX = 0.8): Buffer {
  const floats = (values: number[]) => {
    const bytes = Buffer.alloc(values.length * 4)
    values.forEach((value, index) => bytes.writeFloatLE(value, index * 4))
    return bytes
  }
  const positions = floats([0, 0.9, 0, -0.75, -0.75, 0, 0.75, -0.75, 0])
  const normals = floats([0, 0, 1, 0, 0, 1, 0, 0, 1])
  const joints = Buffer.alloc(3 * 4 * 2)
  const weights = floats([1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0])
  const inverseBind = floats([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])
  const times = floats([0, 2])
  const translations = floats([0, 0, 0, translationEndX, 0, 0])
  const chunks = [positions, normals, joints, weights, inverseBind, times, translations]
  const offsets: number[] = []
  let offset = 0
  for (const chunk of chunks) {
    offsets.push(offset)
    offset += chunk.length
  }
  const bin = Buffer.concat(chunks)
  const gltf = {
    asset: { version: '2.0', generator: 'motion-g1-skinned-e2e' },
    extensionsUsed: ['KHR_materials_unlit'],
    buffers: [{ byteLength: bin.length }],
    bufferViews: chunks.map((chunk, index) => ({ buffer: 0, byteOffset: offsets[index], byteLength: chunk.length })),
    accessors: [
      { bufferView: 0, componentType: 5126, count: 3, type: 'VEC3', min: [-0.75, -0.75, 0], max: [0.75, 0.9, 0] },
      { bufferView: 1, componentType: 5126, count: 3, type: 'VEC3' },
      { bufferView: 2, componentType: 5123, count: 3, type: 'VEC4' },
      { bufferView: 3, componentType: 5126, count: 3, type: 'VEC4' },
      { bufferView: 4, componentType: 5126, count: 1, type: 'MAT4' },
      { bufferView: 5, componentType: 5126, count: 2, type: 'SCALAR', min: [0], max: [2] },
      { bufferView: 6, componentType: 5126, count: 2, type: 'VEC3' },
    ],
    materials: [{ name: 'red-unlit', pbrMetallicRoughness: { baseColorFactor: [1, 0, 0, 1] },
      extensions: { KHR_materials_unlit: {} } }],
    meshes: [{ primitives: [{ attributes: { POSITION: 0, NORMAL: 1, JOINTS_0: 2, WEIGHTS_0: 3 }, material: 0 }] }],
    nodes: [{ mesh: 0, skin: 0 }, { name: 'RootBone' }],
    skins: [{ joints: [1], skeleton: 1, inverseBindMatrices: 4 }],
    animations: [{ name: 'BoneSlide', samplers: [{ input: 5, output: 6, interpolation: 'LINEAR' }],
      channels: [{ sampler: 0, target: { node: 1, path: 'translation' } }] }],
    scenes: [{ nodes: [0, 1] }],
    scene: 0,
  }
  const json = pad4(Buffer.from(JSON.stringify(gltf)), 0x20)
  const binary = pad4(bin, 0)
  const header = Buffer.alloc(12)
  header.write('glTF', 0)
  header.writeUInt32LE(2, 4)
  header.writeUInt32LE(12 + 8 + json.length + 8 + binary.length, 8)
  const jsonHeader = Buffer.alloc(8)
  jsonHeader.writeUInt32LE(json.length, 0)
  jsonHeader.writeUInt32LE(0x4e4f534a, 4)
  const binHeader = Buffer.alloc(8)
  binHeader.writeUInt32LE(binary.length, 0)
  binHeader.writeUInt32LE(0x004e4942, 4)
  return Buffer.concat([header, jsonHeader, json, binHeader, binary])
}
