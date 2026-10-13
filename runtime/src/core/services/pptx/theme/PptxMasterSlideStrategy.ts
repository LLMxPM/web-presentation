/**
 * 文件用途：PPTX 幻灯片母版策略，仅将全篇一致的公共背景和页码提升为母版，严禁将不同页面背景或动态内容错误共享。
 */

import type { PptxSlideBackgroundIR } from '@/core/services/pptx/ir/PptxSlideIR.types'

export interface MasterSlideStrategyResult {
  /** 构造出的母版定义（若无法提取有效公共属性则为 undefined） */
  masterProps?: {
    title: string
    background?: {
      color: string
      transparency?: number
    }
    slideNumber?: {
      x: string
      y: string
      color: string
      fontSize: number
    }
  }
  /** 是否存在全篇统一的公共背景 */
  hasSharedBackground: boolean
}

export const DEFAULT_MASTER_NAME = 'RUNTIME_DEFAULT_MASTER'

/**
 * 幻灯片母版策略器。
 */
export class PptxMasterSlideStrategy {
  /**
   * 评估多页导出的背景集合，判断是否存在可安全提升为母版的统一背景。
   * 约束：仅当全部页面的背景颜色与透明度完全一致时才提升；只要有一页不同，立即放弃统一母版背景，避免覆盖差异页面。
   * @param pageBackgrounds 所有页面的背景描述列表
   * @param showSlideNumber 是否在母版中开启页码
   */
  evaluate(
    pageBackgrounds: Array<PptxSlideBackgroundIR | undefined>,
    showSlideNumber = false,
  ): MasterSlideStrategyResult {
    if (pageBackgrounds.length === 0) {
      return { hasSharedBackground: false }
    }

    const first = pageBackgrounds[0]
    let allIdentical = Boolean(first && first.color)

    if (allIdentical && first) {
      for (let i = 1; i < pageBackgrounds.length; i++) {
        const current = pageBackgrounds[i]
        if (
          !current ||
          current.color.toUpperCase() !== first.color.toUpperCase() ||
          current.transparency !== first.transparency
        ) {
          allIdentical = false
          break
        }
      }
    }

    if (!allIdentical) {
      // 页面背景不一致，母版仅保留页码（若开启），不设母版背景
      return {
        hasSharedBackground: false,
        masterProps: showSlideNumber
          ? {
              title: DEFAULT_MASTER_NAME,
              slideNumber: {
                x: '92%',
                y: '94%',
                color: '888888',
                fontSize: 10,
              },
            }
          : undefined,
      }
    }

    return {
      hasSharedBackground: true,
      masterProps: {
        title: DEFAULT_MASTER_NAME,
        background: {
          color: first!.color,
          transparency: first!.transparency,
        },
        ...(showSlideNumber
          ? {
              slideNumber: {
                x: '92%',
                y: '94%',
                color: '888888',
                fontSize: 10,
              },
            }
          : {}),
      },
    }
  }
}
