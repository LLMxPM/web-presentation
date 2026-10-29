/** 文件功能：校验 Scene 任务的完成依赖与时序约束，不预估结束时间或编译全局时间轴。 */
import { SceneSessionError, type SceneTask } from './types'

export const MAX_SCENE_TASKS = 128
export const MAX_SCENE_DURATION_MS = 3_600_000

/** 检查有界任务图；依赖只以真实完成解锁，ambient 的无限任务不能有后继。 */
export function validateSceneTasks(tasks: ReadonlyMap<string, SceneTask>): void {
  const fail = (message: string, taskId: string): never => { throw new SceneSessionError('SCENE_TASK_INVALID', message, taskId) }
  for (const task of tasks.values()) {
    if (!['blocking', 'ambient'].includes(task.role)) fail('任务必须显式标记 blocking 或 ambient。', task.id)
    if (typeof task.run !== 'function') fail('任务缺少正向执行函数。', task.id)
    if (task.finite !== undefined && typeof task.finite !== 'boolean') fail('finite 必须是布尔值。', task.id)
    if (task.finite === false && task.role !== 'ambient') fail('无限任务只能标记为 ambient。', task.id)
    for (const value of [task.startMs, task.offsetMs]) {
      if (value !== undefined && (!Number.isFinite(value) || value < 0 || value > MAX_SCENE_DURATION_MS)) {
        fail('任务起点与延时必须是非负有限毫秒值，且不超过一小时。', task.id)
      }
    }
    if (task.afterTrack !== undefined) {
      if (task.startMs !== undefined) fail('startMs 与 afterTrack 不能同时声明。', task.id)
      const predecessor = tasks.get(task.afterTrack)
      if (!predecessor) fail('任务依赖的前驱不存在。', task.id)
      if (predecessor.finite === false) fail('不能依赖无限任务完成。', task.id)
    } else if (task.offsetMs !== undefined) fail('offsetMs 只能与 afterTrack 同时声明。', task.id)
  }
  const visited = new Set<string>(), visiting = new Set<string>()
  /** 深度优先检查环；每个节点至多一个完成前驱，避免引入第二套计划编译器。 */
  function visit(id: string): void {
    if (visiting.has(id)) fail('任务完成依赖存在循环。', id)
    if (visited.has(id)) return
    visiting.add(id)
    const predecessor = tasks.get(id)?.afterTrack
    if (predecessor !== undefined) visit(predecessor)
    visiting.delete(id)
    visited.add(id)
  }
  for (const id of tasks.keys()) visit(id)
}

/** 判断失败是否会使某个 blocking 任务无法完成；纯装饰失败不会阻塞页面完成。 */
export function affectsBlockingTask(tasks: ReadonlyMap<string, SceneTask>, failedId: string): boolean {
  return [...tasks.values()].some(task => {
    if (task.role !== 'blocking') return false
    let cursor: SceneTask | undefined = task
    while (cursor) {
      if (cursor.id === failedId) return true
      cursor = cursor.afterTrack === undefined ? undefined : tasks.get(cursor.afterTrack)
    }
    return false
  })
}
