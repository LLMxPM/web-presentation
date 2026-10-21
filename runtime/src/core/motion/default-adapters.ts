/**
 * 文件功能：按轨道类型组合默认适配器。
 *
 * 每个 transport 调用一次工厂创建，DOM 协调器与媒体/模型期限在同页共享；
 * 适配器自身不创建第二套时钟或全局时间轴。
 */
import type { MotionAdapterFactory } from './adapters'
import { createDomMotionAdapterFactory } from './dom-adapter'
import { createMediaMotionAdapter, type MediaMotionAdapterOptions } from './media-adapter'
import { createModelMotionAdapter, type ModelMotionAdapterOptions } from './model-adapter'
import { MOTION_ERROR_UNSUPPORTED, MotionError } from './errors'

export interface DefaultMotionAdapterOptions {
  media?: MediaMotionAdapterOptions
  model?: ModelMotionAdapterOptions
}

/** 创建默认适配器工厂；调用方按 transport 生命周期持有返回的工厂。 */
export function createDefaultMotionAdapterFactory(options: DefaultMotionAdapterOptions = {}): MotionAdapterFactory {
  const domFactory = createDomMotionAdapterFactory()
  return (context) => {
    switch (context.track.type) {
      case 'dom':
        return domFactory(context)
      case 'audio':
      case 'video':
        return createMediaMotionAdapter(context, options.media)
      case 'model3d':
        return createModelMotionAdapter(context, options.model)
      default:
        throw new MotionError(
          MOTION_ERROR_UNSUPPORTED,
          `不支持的轨道类型 ${String((context.track as { type?: unknown }).type)}。`,
        )
    }
  }
}
