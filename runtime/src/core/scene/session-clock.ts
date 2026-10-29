/** 文件功能：提供只向前推进的 Scene 延时时钟；内部冻结不计入 startMs 和依赖延时。 */
export interface SceneClock {
  elapsed(): number
  setSuspended(suspended: boolean): void
}

/** 使用单调时间源累计有效经过时间；不提供 seek、采样或恢复历史状态。 */
export function createSceneClock(now: () => number): SceneClock {
  let previous = now(), elapsed = 0, suspended = false
  /** 每次读取只累计非负增量，避免异常时间源回退产生反向进度。 */
  function read(): number {
    const current = now()
    if (!suspended) elapsed += Math.max(0, current - previous)
    previous = Math.max(previous, current)
    return elapsed
  }
  return {
    elapsed: read,
    setSuspended(next) { read(); suspended = next },
  }
}
