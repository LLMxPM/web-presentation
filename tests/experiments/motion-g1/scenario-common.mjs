// 文件功能：提供 G1 浏览器场景共享的页面读数、挂载和截图像素比较。
/** 读取页面状态与元素测量，供 Node 侧断言。 */
export const readStyle = (page, selector) => page.evaluate(target => window.harness.read(target), selector)
export const readState = page => page.evaluate(() => window.probe.state.value)
export const mount = (page, name, options = {}) => page.evaluate(([scenario, opts]) => window.harness.mount(scenario, opts), [name, options])

/** 停在指定逻辑时刻并返回元素测量。 */
export async function sample(page, atMs, visualMode) {
  return page.evaluate(async ([time, mode]) => {
    const result = await window.probe.sampleAt(time, mode)
    return { result, title: window.harness.read('.title') }
  }, [atMs, visualMode])
}

/** 比较两张图像：返回差异像素占比；严格采样传入阈值 0。 */
export async function imageDiff(page, first, second, threshold = 24) {
  return page.evaluate(async ([a, b, limit]) => {
    const load = src => new Promise((resolveImage, rejectImage) => {
      const image = new Image()
      image.onload = () => resolveImage(image)
      image.onerror = rejectImage
      image.src = src
    })
    const [left, right] = await Promise.all([load(a), load(b)])
    const canvas = document.createElement('canvas')
    canvas.width = left.width
    canvas.height = left.height
    const context = canvas.getContext('2d')
    context.drawImage(left, 0, 0)
    const leftPixels = context.getImageData(0, 0, canvas.width, canvas.height).data
    context.clearRect(0, 0, canvas.width, canvas.height)
    context.drawImage(right, 0, 0)
    const rightPixels = context.getImageData(0, 0, canvas.width, canvas.height).data
    let changed = 0
    for (let index = 0; index < leftPixels.length; index += 4) {
      if (Math.abs(leftPixels[index] - rightPixels[index])
        + Math.abs(leftPixels[index + 1] - rightPixels[index + 1])
        + Math.abs(leftPixels[index + 2] - rightPixels[index + 2]) > limit) changed += 1
    }
    return changed / (leftPixels.length / 4)
  }, [first, second, threshold])
}
