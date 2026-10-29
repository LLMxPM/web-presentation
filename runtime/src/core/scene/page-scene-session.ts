/** 文件功能：管理本页正向任务的准备、依赖调度、完成聚合和取消，不接管媒体或动画的每帧时间。 */
import { createSceneLifetime, waitForScenePrepare } from './session-lifetime'
import { createSceneClock, type SceneClock } from './session-clock'
import { affectsBlockingTask, MAX_SCENE_DURATION_MS, MAX_SCENE_TASKS, validateSceneTasks } from './task-graph'
import { SceneSessionError, type PageSceneOptions, type PageSceneSession, type SceneIssue, type ScenePhase,
  type SceneSnapshot, type SceneTask, type SceneTaskContext } from './types'

interface TaskRun {
  task: SceneTask
  status: 'waiting' | 'running' | 'done' | 'failed'
  completedAt?: number
  blocked: string | null
}

/** 创建一个 generation 的执行会话；define 只在 prepare 执行，静态入口必须由 slot 在创建前拦截。 */
export function createPageSceneSession(options: PageSceneOptions): PageSceneSession {
  const lifetime = createSceneLifetime()
  const tasks = new Map<string, SceneTask>(), runs = new Map<string, TaskRun>()
  const listeners = new Set<(snapshot: SceneSnapshot) => void>()
  let phase: ScenePhase = 'idle', issue: SceneIssue | null = null
  let registrationOpen = false, externalSuspended = false, suspended = false, dispatching = false
  let prepared: Promise<SceneSnapshot> | null = null, started: Promise<SceneSnapshot> | null = null
  let clock: SceneClock | null = null
  let wakeTimer: ReturnType<typeof setTimeout>, deadline: ReturnType<typeof setTimeout>
  let finish!: (snapshot: SceneSnapshot) => void
  const finished = new Promise<SceneSnapshot>(resolve => { finish = resolve })

  /** 每次提供独立快照，监听者不能修改会话内部状态。 */
  function getSnapshot(): SceneSnapshot {
    return { generation: options.generation, phase, hasBlocking: [...tasks.values()].some(task => task.role === 'blocking'),
      blockedTaskIds: [...runs.values()].filter(run => run.blocked && run.status === 'running').map(run => run.task.id),
      issue: issue ? { ...issue } : null }
  }

  /** 发布状态；观察方异常不能使正在播放的页面失去清理机会。 */
  function publish(): void {
    for (const listener of listeners) { try { listener(getSnapshot()) } catch { /* 观察方不参与任务执行。 */ } }
  }

  /** 丢弃旧 generation 的异步结果，并及时终止其释放域。 */
  function live(): boolean {
    if (!lifetime.signal.aborted && options.isCurrent?.() === false) stop()
    return !lifetime.signal.aborted
  }

  /** 停止后不再调度新工作；幂等清理，已经结算的 completed 不被二次结算。 */
  function stop(): void {
    if (lifetime.signal.aborted) return
    registrationOpen = false
    clearTimeout(wakeTimer); clearTimeout(deadline)
    phase = 'stopped'
    lifetime.stop()
    finish(getSnapshot())
    publish()
    listeners.clear()
  }

  /** 失败立即清理全部工作，未知异常只返回稳定摘要，避免暴露任意资源与执行信息。 */
  function fail(error: unknown, taskId?: string): void {
    if (!live()) return
    const known = error instanceof SceneSessionError ? error : null
    issue = { code: known?.code ?? 'SCENE_TASK_FAILED', message: known?.message ?? '页面任务执行失败。', taskId: known?.taskId ?? taskId }
    registrationOpen = false
    phase = 'failed'
    clearTimeout(wakeTimer); clearTimeout(deadline)
    lifetime.stop()
    finish(getSnapshot())
    publish()
    listeners.clear()
  }

  /** 只有全部有限 blocking 实际完成才结算；ambient 保持运行，直到离页 stop。 */
  function checkCompletion(): void {
    if (!live() || !['running', 'blocked'].includes(phase)) return
    if ([...runs.values()].some(run => run.task.role === 'blocking' && run.status !== 'done')) return
    phase = 'completed'
    clearTimeout(deadline)
    finish(getSnapshot())
    publish()
  }

  /** 合并宿主冻结与 blocking 受阻；只冻结后续延时，不提供公开暂停/恢复控制。 */
  function refreshSuspension(): void {
    if (!live() || !clock) return
    const next = externalSuspended || [...runs.values()].some(run => run.task.role === 'blocking' && run.status === 'running' && run.blocked)
    if (next !== suspended) {
      suspended = next
      clock.setSuspended(next)
      clearTimeout(wakeTimer)
      for (const run of runs.values()) {
        if (run.status !== 'running') continue
        try { run.task.setSuspended?.(next) } catch (error) { fail(error, run.task.id); return }
        if (!live()) return
      }
    }
    if (['running', 'blocked'].includes(phase)) {
      const nextPhase = next ? 'blocked' : 'running'
      if (phase !== nextPhase) { phase = nextPhase; publish() }
    }
    if (!next) dispatch()
  }

  /** 每个任务只获得当前会话的信号与清理域；准备期间不能伪造播放受阻。 */
  function context(taskId: string): SceneTaskContext {
    return { generation: options.generation, signal: lifetime.signal, onCleanup: lifetime.onCleanup,
      setBlocked(reason) {
        const run = runs.get(taskId)
        if (!live() || run?.status !== 'running') return
        run.blocked = reason === null ? null : String(reason).slice(0, 240)
        refreshSuspension()
        publish()
      } }
  }

  /** 完成解锁以实际完成时刻为基准的后继；旧 Promise 成败都不能污染新会话。 */
  function settle(run: TaskRun, succeeded: boolean, error?: unknown): void {
    if (!live() || run.status !== 'running') return
    run.status = succeeded ? 'done' : 'failed'
    run.blocked = null
    run.completedAt = clock!.elapsed()
    if (!succeeded && affectsBlockingTask(tasks, run.task.id)) { fail(error, run.task.id); return }
    refreshSuspension()
    checkCompletion()
    dispatch()
  }

  /** 正向经过起点至多启动一次；同步回调和 Promise 使用同一个完成路径。 */
  function startTask(run: TaskRun): void {
    run.status = 'running'
    try {
      Promise.resolve(run.task.run(context(run.task.id))).then(() => settle(run, true), error => settle(run, false, error))
    } catch (error) { settle(run, false, error) }
  }

  /** 只维护尚未启动任务的最近唤醒点；不推测前驱结束，不循环补发过期回调。 */
  function dispatch(): void {
    clearTimeout(wakeTimer)
    if (dispatching || !live() || !clock || suspended || !['running', 'blocked', 'completed'].includes(phase)) return
    dispatching = true
    let earliest = Infinity
    try {
      for (const run of runs.values()) {
        if (!live() || suspended) break
        if (run.status !== 'waiting') continue
        const predecessor = run.task.afterTrack === undefined ? null : runs.get(run.task.afterTrack)
        if (predecessor && predecessor.status !== 'done') continue
        const due = predecessor ? predecessor.completedAt! + (run.task.offsetMs ?? 0) : (run.task.startMs ?? 0)
        if (due <= clock.elapsed()) startTask(run)
        else earliest = Math.min(earliest, due)
      }
    } finally { dispatching = false }
    if (live() && !suspended && Number.isFinite(earliest)) {
      wakeTimer = setTimeout(dispatch, Math.max(1, earliest - clock.elapsed()))
    }
    checkCompletion()
  }

  /** 校验期限并封顶；非法数值不能通过 setTimeout 的溢出行为绕开边界。 */
  function timeout(value: number | undefined, fallback: number, maximum: number): number {
    if (value !== undefined && (!Number.isFinite(value) || value <= 0)) throw new SceneSessionError('SCENE_OPTIONS_INVALID', '会话期限必须是正有限毫秒值。')
    return Math.min(value ?? fallback, maximum)
  }

  /** 注册只在 prepare 开放；图校验通过后并行准备，但整个阶段共享一个期限。 */
  function prepare(): Promise<SceneSnapshot> {
    if (prepared) return prepared
    if (!live()) return Promise.resolve(getSnapshot())
    phase = 'preparing'
    prepared = (async () => {
      try {
        const prepareMs = timeout(options.prepareTimeoutMs, 25_000, 25_000)
        timeout(options.completionTimeoutMs, MAX_SCENE_DURATION_MS, MAX_SCENE_DURATION_MS)
        if (!Number.isSafeInteger(options.generation) || options.generation < 1 || !['manual', 'timer', 'scene_end'].includes(options.advanceMode)) {
          throw new SceneSessionError('SCENE_OPTIONS_INVALID', '会话 generation 或推进模式非法。')
        }
        await waitForScenePrepare(async () => {
          registrationOpen = true
          await options.define({ generation: options.generation, signal: lifetime.signal, onCleanup: lifetime.onCleanup,
            linkSignal(signal) {
              if (signal.aborted) { stop(); return }
              signal.addEventListener('abort', stop, { once: true })
              lifetime.onCleanup(() => signal.removeEventListener('abort', stop))
            },
            register(task) {
              if (!registrationOpen || !live()) throw new SceneSessionError('SCENE_REGISTRATION_CLOSED', '任务只能在当前会话 prepare 注册。')
              if (!task || typeof task.id !== 'string' || !task.id.trim() || task.id.length > 128 || tasks.has(task.id) || tasks.size >= MAX_SCENE_TASKS) {
                throw new SceneSessionError('SCENE_TASK_INVALID', '任务 id 缺失、重复、过长或数量超限。')
              }
              tasks.set(task.id, { ...task })
            } })
          registrationOpen = false
          if (!live()) return
          validateSceneTasks(tasks)
          if (options.advanceMode === 'scene_end' && !getSnapshot().hasBlocking) {
            throw new SceneSessionError('SCENE_COMPLETION_REQUIRED', 'scene_end 页面必须注册有限 blocking 任务。')
          }
          for (const task of tasks.values()) runs.set(task.id, { task, status: 'waiting', blocked: null })
          await Promise.all([...tasks.values()].map(async task => {
            try { if (live()) await task.prepare?.(context(task.id)) }
            catch (error) { fail(error, task.id) }
          }))
        }, lifetime.signal, prepareMs)
        if (live()) { phase = 'ready'; publish() }
      } catch (error) { fail(error) }
      return getSnapshot()
    })()
    publish()
    return prepared
  }

  /** 重复 start 共用一次准备与启动；无 blocking 的手动/计时页立即完成聚合。 */
  function start(): Promise<SceneSnapshot> {
    if (started) return started
    started = prepare().then(() => {
      if (!live() || phase !== 'ready') return getSnapshot()
      clock = createSceneClock(options.now ?? (() => performance.now()))
      phase = 'running'; publish()
      if (!live()) return getSnapshot()
      deadline = setTimeout(() => fail(new SceneSessionError('SCENE_COMPLETION_TIMEOUT', '页面有限任务完成超时。')),
        timeout(options.completionTimeoutMs, MAX_SCENE_DURATION_MS, MAX_SCENE_DURATION_MS))
      refreshSuspension()
      return getSnapshot()
    })
    return started
  }

  return { getSnapshot, prepare, start, finished, stop,
    setSuspended(value) { externalSuspended = value; refreshSuspension() },
    subscribe(listener) { if (lifetime.signal.aborted) return () => {}; listeners.add(listener); return () => { listeners.delete(listener) } },
  }
}
