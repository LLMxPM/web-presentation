/** 文件功能：定义三维查看器展示参数与内部控制器接口，不向页面暴露 Three.js 共享对象。 */
export interface ModelViewerProps {
  /** 资源逻辑名，用于 manifest render_type 校验与诊断。 */
  name?: string
  /** 已由 resolveResourcePath 解析好的 GLB 地址（含预览票据）。 */
  src?: string
  /** 源文件场景索引；缺省取 glTF 默认场景，仍缺省时取第一个有效场景。 */
  sceneIndex?: number
  /** 源文件相机索引，须属于选中场景。 */
  cameraIndex?: number
  /** 显式相机位置。 */
  cameraPosition?: [number, number, number]
  /** 显式相机目标。 */
  cameraTarget?: [number, number, number]
  /** 显式相机垂直视场角（度）。 */
  cameraFov?: number
  /** 背景色：transparent 或 #RGB/#RRGGBB/#RRGGBBAA。 */
  background?: string
  /** 光照来源。 */
  lighting?: 'auto' | 'source'
  /** 是否启用查看交互。 */
  interactive?: boolean
  /** 兜底文案。 */
  fallback?: string
}


export interface OrbitControlsLike {
  enableDamping?: boolean
  /** 轨道中心；默认值在原点，必须在首次 update 前显式对齐当前相机姿态。 */
  target?: { copy: (target: { x: number; y: number; z: number }) => void }
  update: () => void
  dispose: () => void
  addEventListener?: (type: 'change', listener: () => void) => void
  removeEventListener?: (type: 'change', listener: () => void) => void
}
