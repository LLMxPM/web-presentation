/**
 * 文件用途：定义三维模型（model3d）静态帧的跨模块共享契约：
 * DOM 采集句柄属性、覆盖层标记属性、实例身份结构与帧查找逻辑。
 *
 * 契约分三层，跨 realm（离屏 iframe 舞台）同样成立：
 * - 采集句柄：ModelViewer 挂载时把句柄对象挂到根元素属性
 *   MODEL_STATIC_FRAME_HANDLE_KEY 上，卸载时注销；属性名是固定字符串，
 *   iframe 与宿主窗口各自求值得到相同取值，因此宿主可以跨 realm 读取该句柄。
 * - 覆盖层：prepare 阶段插入带 MODEL_STATIC_FRAME_IMG_ATTR 的 `<img>`，
 *   PPTX 转换器按该标记找到静态帧图片块；其他图片元素不会被误认。
 * - 身份结构：句柄返回资源身份与视角键，供静态帧缓存分区使用。
 */

/** 静态帧 DOM 契约版本；标记取值与该值不一致时一律视为未声明契约。 */
export const MODEL_STATIC_FRAME_VERSION = 'v1'

/**
 * 覆盖层 `<img>` 标记属性；值只承载契约版本。
 * 说明：必须使用固定字符串属性名而非 Symbol，克隆 DOM 与会话内跨 Window 读写都只依赖字符串相等。
 */
export const MODEL_STATIC_FRAME_IMG_ATTR = 'data-runtime-model-frame'

/**
 * ModelViewer 根元素上的采集句柄属性名。
 * 关键约束：属性名是跨 realm 的字符串契约，改名等于破坏导出链路，需同步全部消费者与测试。
 */
export const MODEL_STATIC_FRAME_HANDLE_KEY = '__runtimeModelStaticFrameHandleV1'

/**
 * 实例帧身份：静态帧缓存的分区依据。
 * 缓存键必须包含资源身份 + 视角参数 + 视口尺寸（含 DPR），相同资源不同视角不得共用帧。
 */
export interface ModelStaticFrameIdentity {
  /** 资源逻辑名（asset.name）。 */
  resourceName: string
  /** 已解析的资源地址（含文件身份与预览票据），用于区分同名不同版本。 */
  resourceSrc: string
  /** 实例视角键：场景/相机/position/target/fov/背景与光照策略。 */
  viewKey: string
  /** 帧像素宽度（= 视口 CSS 宽度 × 已收敛 DPR）。 */
  frameWidth: number
  /** 帧像素高度。 */
  frameHeight: number
}

/** 采集结果：当前帧 PNG dataURL 与采集时刻的实例身份。 */
export interface ModelStaticFrameCapture extends ModelStaticFrameIdentity {
  /** `data:image/png;base64,...` 形式的 PNG 数据地址。 */
  dataUrl: string
}

/**
 * ModelViewer 实例向宿主注册的采集句柄。
 * describe / capture 均为同步调用：未就绪、未渲染或上下文丢失时返回 null，不抛异常。
 */
export interface ModelStaticFrameHandle {
  /** 读取当前实例身份；未就绪时返回 null。 */
  describe(): ModelStaticFrameIdentity | null
  /** 同步重绘后立即读回当前帧 PNG 与身份；失败时返回 null。 */
  capture(): ModelStaticFrameCapture | null
}

/**
 * 从模型根元素读取已注册的采集句柄。
 * 说明：句柄可能来自 iframe realm，不能使用 instanceof 判定，只做鸭子类型校验。
 * @param element 候选模型根元素
 * @returns 可用的采集句柄；未注册或形状不合法时返回 null
 */
export function readModelStaticFrameHandle(element: Element): ModelStaticFrameHandle | null {
  const candidate = (element as unknown as Record<string, unknown>)[MODEL_STATIC_FRAME_HANDLE_KEY]
  if (!candidate || typeof candidate !== 'object') {
    return null
  }
  const record = candidate as { describe?: unknown; capture?: unknown }
  if (typeof record.describe !== 'function' || typeof record.capture !== 'function') {
    return null
  }
  return candidate as ModelStaticFrameHandle
}

/**
 * 判断元素是否为 prepare 阶段插入的静态帧覆盖图。
 * 说明：覆盖图是模型根节点的直接子元素（整块覆盖画布），按直接子级匹配避免误命中嵌套结构。
 * @param element 候选元素
 * @returns 是否为当前版本的静态帧覆盖图
 */
export function isModelStaticFrameImage(element: Element): boolean {
  return element.tagName.toLowerCase() === 'img' &&
    element.getAttribute(MODEL_STATIC_FRAME_IMG_ATTR) === MODEL_STATIC_FRAME_VERSION
}

/**
 * 在模型根元素的直接子级中查找静态帧覆盖图。
 * @param root 模型根元素（data-runtime-kit-media-kind="model3d" 节点）
 * @returns 覆盖图 `<img>`；未准备时返回 null
 */
export function findModelStaticFrameImage(root: Element): HTMLImageElement | null {
  for (const child of Array.from(root.children)) {
    if (isModelStaticFrameImage(child)) {
      return child as HTMLImageElement
    }
  }
  return null
}
