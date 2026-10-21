// 文件功能：WP01 原生 WAAPI 候选后端；动画保持暂停，由同一个绝对逻辑时间驱动。

/** 创建 opacity 与 transform 分离轨道，外层布局变换不归本后端所有。 */
export function createDom(targets) {
  targets.forEach(target => { target.style.willChange = 'transform, opacity' })
  const animations = targets.flatMap((target, i) => [
    target.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 800, delay: i * 15, fill: 'both', easing: 'linear' }),
    target.animate([{ transform: 'translateY(60px)' }, { transform: 'translateY(0px)' }], { duration: 800, delay: i * 15, fill: 'both', easing: 'linear' }),
  ])
  animations.forEach(animation => { animation.pause(); animation.currentTime = 0 })
  return {
    sample(ms) { animations.forEach(animation => { animation.currentTime = ms }) },
    freeze() { animations.forEach(animation => { animation.commitStyles(); animation.cancel() }) },
    dispose() { animations.forEach(animation => animation.cancel()); targets.forEach(target => { target.style.willChange = '' }) },
    count() { return animations.filter(animation => animation.playState !== 'idle').length },
  }
}
