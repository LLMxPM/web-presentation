// 文件功能：运行时向候选实际使用的时间轴加入无媒体副作用的探针，验证静默定位而非只检查布尔参数。

/** 在候选导入前包装公开时间控制方法；只在被测 sample 调用期间插入一次计数回调。 */
export async function installProbe(page, engine, base) {
  await page.evaluate(async ({ engine, base }) => {
    const probe = window.lunaCallbackProbe = { active: false, events: [], timelines: 0 }
    const installed = new WeakSet()
    if (engine === 'gsap') {
      const { gsap } = await import(`${base}/gsap/index.js`)
      const prototype = gsap.core.Timeline.prototype
      for (const method of ['time', 'totalTime', 'seek']) {
        const original = prototype[method]
        prototype[method] = function (...args) {
          if (probe.active && args.length && !installed.has(this)) {
            installed.add(this); probe.timelines++
            this.call(() => probe.events.push('probe'), [], 0.1)
          }
          return original.apply(this, args)
        }
      }
    } else {
      const { createTimeline } = await import(`${base}/animejs/dist/modules/index.js`)
      const temporary = createTimeline({ autoplay: false }), prototype = Object.getPrototypeOf(temporary), original = prototype.seek
      temporary.cancel()
      prototype.seek = function (...args) {
        if (probe.active && args.length && !installed.has(this)) {
          installed.add(this); probe.timelines++
          this.call(() => probe.events.push('probe'), 100)
        }
        return original.apply(this, args)
      }
    }
  }, { engine, base })
}
