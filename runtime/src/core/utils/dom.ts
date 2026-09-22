/**
 * DOM 操作相关工具函数
 */

/**
 * 等待页面加载完成
 * @param timeout 超时时间(毫秒)
 * @returns Promise<void>
 */
export async function waitForPageLoad(timeout: number = 15000): Promise<void> {
  return new Promise((resolve) => {
    const startTime = Date.now()
    
    const checkReady = () => {
      // 检查多个条件确保页面真正加载完成
      const isDocumentReady = document.readyState === 'complete'
      const isVueReady = checkVueAppReady()
      
      if (isDocumentReady && isVueReady) {
        // 额外等待一小段时间确保所有资源加载完成
        setTimeout(resolve, 300)
        return
      }
      
      if (Date.now() - startTime > timeout) {
        console.warn('页面加载超时，但继续执行')
        resolve() // 不抛出错误，允许继续执行
        return
      }
      
      setTimeout(checkReady, 100)
    }
    
    checkReady()
  })
}

/**
 * 检查Vue应用是否准备就绪
 * @returns 是否准备就绪
 */
function checkVueAppReady(): boolean {
  try {
    const appElement = document.querySelector('#app')
    if (!appElement) return true // 如果没有Vue应用，认为准备就绪
    
    // 检查Vue应用是否已挂载
    const hasContent = appElement.children.length > 0
    
    return hasContent // 简化检查，只要有内容就认为准备就绪
  } catch (error) {
    console.warn('检查Vue应用状态时出错:', error)
    return true // 出错时假设准备就绪
  }
}

/**
 * 等待图片加载完成
 * @param element 包含图片的元素
 * @returns Promise<void>
 */
export async function waitForImages(element: HTMLElement): Promise<void> {
  const images = element.querySelectorAll('img')
  const imagePromises: Promise<void>[] = []
  
  images.forEach(img => {
    if (img.complete && img.naturalWidth > 0) {
      return // 图片已加载完成
    }
    
    const promise = new Promise<void>((resolve) => {
      const timeout = setTimeout(() => {
        console.warn(`图片加载超时: ${img.src}`)
        resolve() // 超时时继续，不阻塞整个流程
      }, 5000) // 减少单个图片的超时时间
      
      img.onload = () => {
        clearTimeout(timeout)
        resolve()
      }
      
      img.onerror = () => {
        clearTimeout(timeout)
        console.warn(`图片加载失败: ${img.src}`)
        resolve() // 即使图片加载失败也继续
      }
      
      // 如果图片没有src，直接resolve
      if (!img.src || img.src === '') {
        clearTimeout(timeout)
        resolve()
      }
    })
    
    imagePromises.push(promise)
  })
  
  try {
    await Promise.all(imagePromises)
  } catch (error) {
    console.warn('部分图片加载失败:', error)
    // 不抛出错误，允许继续执行
  }
}

/**
 * 查找页面主要内容区域
 * @returns HTMLElement | null
 */
export function findContentElement(): HTMLElement | null {
  // 按优先级查找内容区域，增加更多选择器
  const selectors = [
    '.fixed-ratio-container',
    '.page-content-wrapper',
    // 页面特定内容区域
    '.page-content',           // 页面内容区域
    '.main-content',           // 主内容区域
    '.content-wrapper',        // 内容包装器
    '.app-content',            // 应用内容区域
    '[data-content]',          // 带有data-content属性的元素
    '.content',                // 通用内容区域
    '[role="main"]',          // 语义化主内容区域
    'main',                    // HTML5 main标签
    
    // Vue应用结构
    '#app > div:first-child',  // Vue应用的根元素
    '#app > .layout',          // 布局组件
    '#app > main',             // 主内容组件
    '#app'                     // Vue应用容器
  ]
  
  for (const selector of selectors) {
    try {
      const element = document.querySelector(selector) as HTMLElement
      if (element && isValidContentElement(element)) {
        return element
      }
    } catch (error) {
      console.warn(`查找元素失败: ${selector}`, error)
    }
  }
  
  // 如果都没找到，返回body
  console.warn('未找到理想的内容元素，使用body')
  return document.body
}

/**
 * 验证元素是否为有效的内容元素
 * @param element 要验证的元素
 * @returns 是否有效
 */
function isValidContentElement(element: HTMLElement | null): element is HTMLElement {
  if (!element) return false
  
  try {
    // 检查元素是否可见且有尺寸
    const rect = element.getBoundingClientRect()
    const computedStyle = window.getComputedStyle(element)
    
    const isVisible = (
      rect.width > 0 && 
      rect.height > 0 && 
      computedStyle.visibility !== 'hidden' &&
      computedStyle.display !== 'none' &&
      parseFloat(computedStyle.opacity) > 0
    )
    
    // 检查元素尺寸是否合理（至少100x100像素）
    const hasReasonableSize = rect.width >= 100 && rect.height >= 100
    
    return isVisible && hasReasonableSize
  } catch (error) {
    console.warn('验证元素有效性时出错:', error)
    return false
  }
}

/**
 * 获取页面尺寸
 * @returns 页面尺寸对象
 */
export function getPageDimensions(): { width: number; height: number } {
  const contentElement = findContentElement()
  if (contentElement) {
    const rect = contentElement.getBoundingClientRect()
    return {
      width: rect.width,
      height: rect.height
    }
  }
  
  return {
    width: window.innerWidth,
    height: window.innerHeight
  }
}
