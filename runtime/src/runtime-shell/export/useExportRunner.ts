/**
 * 文件用途：封装导出弹窗的任务执行、进度上报、取消与服务路由注入，隔离三种导出服务的分派细节。
 *
 * 取消语义：cancelExport 会推进内部运行序号，在飞的服务调用之后 settle 时被判定为过期并整体丢弃 ——
 * 既不覆盖已写入的取消结果，也不补发 export-complete / export-error。
 */

import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { browserPrintService } from '@/core/services/BrowserPrintService'
import { pdfExportService } from '@/core/services/PDFExportService'
import { pptxExportService } from '@/core/services/PPTXExportService'
import type { ExportMode, ExportProgress } from '@/core/types/export-common'
import type { ExportMethod, ExportOptions } from '@/core/types/pdf-export'
import type { PptxExportOptions } from '@/core/types/pptx-export'
import type { DialogExportMethod, DialogExportResult } from './export-dialog-types'

/**
 * 一次导出请求的输入。
 */
export interface ExportRunRequest {
  /** 导出方式 */
  method: DialogExportMethod
  /** 导出范围 */
  mode: ExportMode
  /** 用户自定义文件名，留空时由各服务按标题与时间戳生成 */
  filename?: string
}

/**
 * 运行事件回调；被取消或被新任务取代的过期运行不会触发任何回调。
 */
export interface ExportRunListener {
  /** 任务已发起 */
  onStart?: () => void
  /** 任务成功完成 */
  onComplete?: (result: DialogExportResult) => void
  /** 任务失败 */
  onError?: (error: Error) => void
}

/** 单次导出调用签名；进度回调只有逐页导出的服务会真正触发。 */
type ExportInvoker = (
  request: ExportRunRequest,
  onProgress: (progress: ExportProgress) => void,
) => Promise<DialogExportResult>

const EMPTY_PROGRESS: ExportProgress = {
  current: 0,
  total: 0,
  percentage: 0,
  currentPageTitle: '',
  currentPageRoute: '',
}

/**
 * 构造 PDF 与浏览器打印服务共用的导出参数。
 * @param request 导出请求
 * @param method PDF 侧的生成方式
 * @returns PDF 导出参数
 */
function toPdfOptions(request: ExportRunRequest, method: ExportMethod): ExportOptions {
  return {
    mode: request.mode,
    method,
    filename: request.filename,
  }
}

/**
 * 构造 PPTX 导出参数。
 * @param request 导出请求
 * @returns PPTX 导出参数
 */
function toPptxOptions(request: ExportRunRequest): PptxExportOptions {
  return {
    mode: request.mode,
    filename: request.filename,
  }
}

/** 方式 × 范围的服务分派表；新增导出方式只需在此登记，不必改动执行流程。 */
const RUNNERS: Record<DialogExportMethod, Record<ExportMode, ExportInvoker>> = {
  'pptx-editable': {
    current: request => pptxExportService.exportCurrentPage(toPptxOptions(request)),
    all: (request, onProgress) => pptxExportService.exportAllPages(toPptxOptions(request), onProgress),
  },
  'browser-print': {
    current: request => browserPrintService.printCurrentPage(toPdfOptions(request, 'browser-print')),
    all: (request, onProgress) => browserPrintService.printAllPages(toPdfOptions(request, 'browser-print'), onProgress),
  },
  'canvas-pdf': {
    current: request => pdfExportService.exportCurrentPage(toPdfOptions(request, 'canvas-pdf')),
    all: (request, onProgress) => pdfExportService.exportAllPages(toPdfOptions(request, 'canvas-pdf'), onProgress),
  },
}

/** 各导出方式的取消入口。 */
const CANCELLERS: Record<DialogExportMethod, () => void> = {
  'pptx-editable': () => pptxExportService.cancelExport(),
  'browser-print': () => browserPrintService.cancelPrint(),
  'canvas-pdf': () => pdfExportService.cancelExport(),
}

/**
 * 构造失败结果。
 * @param method 导出方式
 * @param message 失败原因
 * @returns 弹窗可直接展示的失败结果
 */
function buildFailureResult(method: DialogExportMethod, message: string): DialogExportResult {
  const failure = {
    success: false,
    taskId: '',
    filename: '',
    pageCount: 0,
    duration: 0,
    error: message,
  }

  // PPTX 结果的 method 是字面量 'pptx-editable'，与 PDF/打印的 ExportMethod 不互相兼容，必须分别收窄。
  return method === 'pptx-editable'
    ? { ...failure, method: 'pptx-editable' }
    : { ...failure, method }
}

/**
 * 导出运行器：持有导出态、进度与结果，并在 setup 期间把当前路由注入三个导出服务单例。
 * @param listener 运行事件回调
 * @returns 导出态与执行、取消、重置入口
 */
export function useExportRunner(listener: ExportRunListener = {}) {
  const router = useRouter()
  const isExporting = ref(false)
  const exportResult = ref<DialogExportResult | null>(null)
  const progress = ref<ExportProgress>({ ...EMPTY_PROGRESS })

  /** 单调递增的运行序号；取消或发起新任务都会推进它，用于识别并丢弃迟到的 settle 结果。 */
  let activeRunId = 0

  onMounted(() => {
    pdfExportService.setRouter(router)
    browserPrintService.setRouter(router)
    pptxExportService.setRouter(router)
  })

  /**
   * 清空上一次运行的结果与进度，回到可再次发起导出的状态。
   */
  function resetRun(): void {
    exportResult.value = null
    progress.value = { ...EMPTY_PROGRESS }
  }

  /**
   * 发起一次导出；同一时刻只允许一个运行，重复调用直接忽略。
   * @param request 导出请求
   */
  async function startExport(request: ExportRunRequest): Promise<void> {
    if (isExporting.value) {
      return
    }

    const runId = ++activeRunId
    isExporting.value = true
    exportResult.value = null
    listener.onStart?.()

    try {
      const result = await RUNNERS[request.method][request.mode](request, data => {
        if (runId === activeRunId) {
          progress.value = data
        }
      })

      if (runId !== activeRunId) {
        return
      }

      exportResult.value = result
      listener.onComplete?.(result)
    } catch (error) {
      if (runId !== activeRunId) {
        return
      }

      const normalized = error instanceof Error ? error : new Error('导出失败')
      exportResult.value = buildFailureResult(request.method, normalized.message)
      listener.onError?.(normalized)
    } finally {
      // 过期运行的 finally 不得回写运行态：取消路径已经把 isExporting 置回 false。
      if (runId === activeRunId) {
        isExporting.value = false
      }
    }
  }

  /**
   * 取消当前导出，并让在飞的服务调用结果整体作废。
   * @param method 正在执行的导出方式
   */
  function cancelExport(method: DialogExportMethod): void {
    if (!isExporting.value) {
      return
    }

    CANCELLERS[method]()
    activeRunId += 1
    isExporting.value = false
    exportResult.value = buildFailureResult(method, '用户取消导出')
  }

  return {
    isExporting,
    exportResult,
    progress,
    startExport,
    cancelExport,
    resetRun,
  }
}
