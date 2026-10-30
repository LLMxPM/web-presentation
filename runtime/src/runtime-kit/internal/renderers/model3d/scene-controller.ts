/** 文件功能：为独立模型实例创建正向 Mixer 任务，按真实 finished 聚合，统一冻结、取消和片段失效校验。 */
import type * as Three from 'three'
import { SceneSessionError, type SceneTask, type SceneTaskContext } from '@/core/scene/types'
import type { Model3dEngine, ParsedModelResource } from './engine'
import type { ModelSceneAnimation, ModelSceneHandle } from './scene-contract'

interface ModelSceneOptions {
  engine: Model3dEngine; parsed: ParsedModelResource; root: Three.Object3D; wrapper: Three.Group; camera: Three.Camera
  target: Three.Vector3
  isReady(): boolean
  isStatic(): boolean
  render(): void
}
interface RunningAction {
  context: SceneTaskContext; action: Three.AnimationAction; stop(): void; reject(error: unknown): void
}

/** 一个加载实例拥有一个 Mixer 与至多一个正在执行的动作；共享缓存始终只读。 */
export function createModelSceneController(options: ModelSceneOptions) {
  const { engine, parsed, root, wrapper } = options
  const mixer = new engine.THREE.AnimationMixer(root)
  let current: RunningAction | null = null, disposed = false, suspended = false, viewerSuspended = false
  let completedAction: Three.AnimationAction | null = null
  let frame: number | null = null, previous: number | null = null
  const transform = { x: 0, y: 0, z: 0, scale: 1, rotationY: 0 }
  const camera = { x: options.camera.position.x, y: options.camera.position.y, z: options.camera.position.z,
    targetX: options.target.x, targetY: options.target.y, targetZ: options.target.z,
    fov: (options.camera as Three.PerspectiveCamera).fov ?? 45 }
  const initialCamera = { ...camera }
  const initialQuaternion = options.camera.quaternion.clone(), initialUp = options.camera.up.clone()

  /** 每次开始前复核真实资源索引及签名，不根据片段名称或旧时长猜测。 */
  function validate(input: ModelSceneAnimation): Three.AnimationClip {
    if (disposed || !options.isReady() || options.isStatic()) throw new SceneSessionError('MODEL_SCENE_UNAVAILABLE', '模型尚未就绪或当前为静态执行。', input.id)
    const clip = Number.isSafeInteger(input.clipIndex) && input.clipIndex >= 0 ? parsed.animations[input.clipIndex] : undefined
    if (!clip || !input.signature || parsed.animationSignatures?.[input.clipIndex] !== input.signature) {
      throw new SceneSessionError('MODEL_CLIP_STALE', '模型片段索引或签名已经失效，请重新读取资源片段。', input.id)
    }
    const repeat = input.repeat ?? 0, rate = input.rate ?? 1
    if (!Number.isFinite(clip.duration) || clip.duration <= 0 || !Number.isInteger(repeat) || repeat < -1 || repeat > 1000
      || (repeat === -1 && input.role !== 'ambient') || !Number.isFinite(rate) || rate < 0.01 || rate > 16) {
      throw new SceneSessionError('MODEL_ANIMATION_INVALID', '片段必须有有限正时长；无限重复只允许 ambient，速率必须正向。', input.id)
    }
    return clip
  }

  /** 只使用单调正向 delta，恢复后的第一帧重新取基线，不补跑后台时长。 */
  function tick(timestamp: number): void {
    frame = null
    if (!current || suspended || viewerSuspended || disposed) return
    const delta = previous === null ? 0 : Math.max(0, timestamp - previous) / 1000
    previous = timestamp
    try { mixer.update(delta); options.render() } catch (error) { current?.reject(error); return }
    if (current && !suspended && !viewerSuspended) frame = requestAnimationFrame(tick)
  }

  /** 清除唯一 RAF 与旧时钟基线，动作对象由拥有者自己的清理域处理。 */
  function cancelFrame(): void { if (frame !== null) cancelAnimationFrame(frame); frame = null; previous = null }
  /** 合并 Scene 冻结和 Viewer 可见性/上下文状态，任一来源仍冻结时都不得推进。 */
  function updateSuspension(): void {
    cancelFrame()
    if (current && !suspended && !viewerSuspended && !disposed) frame = requestAnimationFrame(tick)
  }

  /** 注册延时与完成词汇直接沿用 Scene，每项任务的回调和事件只结算一次。 */
  function animation(input: ModelSceneAnimation): SceneTask {
    const spec = { ...input }
    let prepared = false, owner: RunningAction | null = null, taskSuspended = false
    return { id: spec.id, role: spec.role, finite: spec.repeat !== -1, startMs: spec.startMs, afterTrack: spec.afterTrack, offsetMs: spec.offsetMs,
      prepare(context) { validate(spec); prepared = true; context.onCleanup(() => { owner?.stop(); reset() }) },
      run(context) {
        const clip = validate(spec)
        if (!prepared || context.signal.aborted) throw new SceneSessionError('MODEL_SCENE_UNAVAILABLE', '模型任务未准备或已经取消。', spec.id)
        if (current) throw new SceneSessionError('MODEL_ACTION_OWNED', '同一模型实例不能同时运行两个动作，请使用独立实例或 afterTrack。', spec.id)
        return new Promise<void>((resolve, reject) => {
          const action = mixer.clipAction(clip)
          let settled = false
          /** 先撤销事件与所有权，再停止动作，迟到 finished 不会结算新任务。 */
          const stop = () => {
            mixer.removeEventListener('finished', finished)
            if (current === owner) { current = null; cancelFrame() }
            action.stop()
            if (completedAction === action) completedAction = null
            if (!settled) { settled = true; resolve() }
          }
          const fail = (error: unknown) => { if (!settled) { settled = true; stop(); reject(error) } }
          /** Three.js finished 是实际完成事实，不能用预估 duration 的 timer 代替。 */
          const finished = (event: { action: Three.AnimationAction }) => {
            if (event.action !== action || settled || current !== owner) return
            settled = true; mixer.removeEventListener('finished', finished); completedAction = action; current = null; cancelFrame(); resolve()
          }
          owner = { context, action, stop, reject: fail }; current = owner
          suspended = taskSuspended
          mixer.addEventListener('finished', finished)
          try {
            // 保留上一动作终态直到下一段开始；开始前释放权重，避免两个 clamp 终态被 Mixer 混成平均姿态。
            completedAction?.stop(); completedAction = null
            action.reset(); action.enabled = true; action.clampWhenFinished = true
            action.setLoop(spec.repeat === -1 ? engine.THREE.LoopRepeat : (spec.repeat ?? 0) > 0 ? engine.THREE.LoopRepeat : engine.THREE.LoopOnce,
              spec.repeat === -1 ? Infinity : (spec.repeat ?? 0) + 1)
            action.setEffectiveTimeScale(spec.rate ?? 1); action.setEffectiveWeight(1); action.play()
            updateSuspension()
          } catch (error) { fail(error) }
        })
      },
      setSuspended(value) { taskSuspended = value; if (current === owner) { suspended = value; updateSuspension() } },
    }
  }

  /** 数值副本可供受管 GSAP 使用；值非法时明确失败，绝不下放共享对象写权限。 */
  function invalidate(): void {
    if (disposed || options.isStatic()) return
    if (![...Object.values(transform), ...Object.values(camera)].every(Number.isFinite) || transform.scale <= 0 || camera.fov <= 0 || camera.fov >= 180) {
      throw new SceneSessionError('MODEL_TRANSFORM_INVALID', '模型变换与相机必须是有限数值，比例和视场角必须有效。')
    }
    wrapper.position.set(transform.x, transform.y, transform.z); wrapper.scale.setScalar(transform.scale)
    wrapper.rotation.set(0, transform.rotationY * Math.PI / 180, 0); wrapper.updateMatrixWorld(true)
    options.camera.position.set(camera.x, camera.y, camera.z)
    options.camera.lookAt(camera.targetX, camera.targetY, camera.targetZ)
    const perspective = options.camera as Three.PerspectiveCamera
    if (perspective.isPerspectiveCamera) { perspective.fov = camera.fov; perspective.updateProjectionMatrix() }
    options.render()
  }
  /** 页面离场恢复独立初始值，Mixer 的 stop 会恢复被该动作管理的节点。 */
  function reset(): void {
    if (disposed) return
    Object.assign(transform, { x: 0, y: 0, z: 0, scale: 1, rotationY: 0 }); Object.assign(camera, initialCamera); invalidate()
    options.camera.quaternion.copy(initialQuaternion); options.camera.up.copy(initialUp); options.camera.updateMatrixWorld(true)
  }
  const handle: ModelSceneHandle = { isReady: () => !disposed && options.isReady(), transform, camera, animation, invalidate, reset,
    animations: () => disposed ? [] : parsed.animations.map((clip, index) => ({ index, name: clip.name || null, durationMs: clip.duration * 1000,
      channelCount: clip.tracks.length, signature: parsed.animationSignatures?.[index] ?? null })),
  }
  return { handle,
    setViewerSuspended(value: boolean) { viewerSuspended = value; updateSuspension() },
    setBlocked(reason: string | null) { current?.context.setBlocked(reason) },
    dispose() { if (disposed) return; disposed = true; current?.reject(new SceneSessionError('MODEL_INSTANCE_REPLACED', '模型实例已释放或资源已经替换。')); cancelFrame(); mixer.stopAllAction(); mixer.uncacheRoot(root) },
  }
}
