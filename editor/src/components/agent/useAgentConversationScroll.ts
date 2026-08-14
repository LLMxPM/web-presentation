/**
 * 文件功能：统一管理智能体会话正文的用户滚动意图、流式贴底调度与内容尺寸观察。
 */
import { nextTick, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'

const USER_SCROLL_INTENT_WINDOW_MS = 1000
const ATTACH_BOTTOM_DISTANCE_PX = 24
type UserScrollDirection = 'up' | 'down' | 'scrollbar'

interface AgentConversationScrollOptions {
  scrollContainerRef: Ref<HTMLElement | null>
  scrollContentRef: Ref<HTMLElement | null>
  sessionKey: () => string | null
}

/**
 * 为会话正文建立单一滚动控制器；所有程序化贴底最终合并到动画帧中执行一次。
 */
export function useAgentConversationScroll(options: AgentConversationScrollOptions) {
  const followingBottom = ref(true)
  let scrollAnimationFrame: number | null = null
  let nextTickPending = false
  let userScrollIntentUntil = 0
  let userScrollDirection: UserScrollDirection | null = null
  let scrollbarDragging = false
  let touchClientY: number | null = null
  let contentResizeObserver: ResizeObserver | null = null

  /** 用户主动离开底部时立即停止跟随，并取消尚未执行的贴底写入。 */
  function detachFromBottom() {
    followingBottom.value = false
    if (scrollAnimationFrame !== null) {
      window.cancelAnimationFrame(scrollAnimationFrame)
      scrollAnimationFrame = null
    }
  }

  /** 记录短期用户意图，避免把程序触发的 scroll 误认为重新贴底。 */
  function markUserScrollIntent(direction: UserScrollDirection) {
    userScrollDirection = direction
    userScrollIntentUntil = performance.now() + USER_SCROLL_INTENT_WINDOW_MS
  }

  function currentUserScrollDirection(): UserScrollDirection | null {
    if (scrollbarDragging) {
      return 'scrollbar'
    }
    return performance.now() <= userScrollIntentUntil ? userScrollDirection : null
  }

  /**
   * 判断滚轮是否会被正文内的独立滚动区消费，避免滚动思考块时关闭外层自动跟随。
   */
  function nestedScrollerCanConsume(target: EventTarget | null, deltaY: number) {
    const container = options.scrollContainerRef.value
    let element = target instanceof HTMLElement ? target : null
    while (element && element !== container) {
      const style = window.getComputedStyle(element)
      const scrollable = /(auto|scroll)/.test(style.overflowY) && element.scrollHeight > element.clientHeight
      if (scrollable) {
        const distanceToBottom = element.scrollHeight - element.scrollTop - element.clientHeight
        if ((deltaY < 0 && element.scrollTop > 0) || (deltaY > 0 && distanceToBottom > 1)) {
          return true
        }
      }
      element = element.parentElement
    }
    return false
  }

  /** 向上滚轮应在浏览器实际移动视口前停止贴底，防止下一批流式内容把用户拉回底部。 */
  function handleWheel(event: WheelEvent) {
    if (!event.deltaY || nestedScrollerCanConsume(event.target, event.deltaY)) {
      return
    }
    markUserScrollIntent(event.deltaY < 0 ? 'up' : 'down')
    if (event.deltaY < 0) {
      detachFromBottom()
    }
  }

  function handleTouchStart(event: TouchEvent) {
    touchClientY = event.touches[0]?.clientY ?? null
  }

  /** 手指向下移动代表查看更早内容，应立即停止贴底。 */
  function handleTouchMove(event: TouchEvent) {
    const nextClientY = event.touches[0]?.clientY ?? null
    if (touchClientY === null || nextClientY === null) {
      touchClientY = nextClientY
      return
    }
    const fingerDelta = nextClientY - touchClientY
    touchClientY = nextClientY
    if (!fingerDelta || nestedScrollerCanConsume(event.target, -fingerDelta)) {
      return
    }
    markUserScrollIntent(fingerDelta > 0 ? 'up' : 'down')
    if (fingerDelta > 0) {
      detachFromBottom()
    }
  }

  function handleTouchEnd() {
    touchClientY = null
  }

  /** 键盘向上浏览时停止跟随；向下或 End 到达底部后由 scroll 事件重新开启。 */
  function handleKeydown(event: KeyboardEvent) {
    const upwardKeys = new Set(['ArrowUp', 'PageUp', 'Home'])
    const downwardKeys = new Set(['ArrowDown', 'PageDown', 'End'])
    if (!upwardKeys.has(event.key) && !downwardKeys.has(event.key)) {
      return
    }
    markUserScrollIntent(upwardKeys.has(event.key) ? 'up' : 'down')
    if (upwardKeys.has(event.key)) {
      detachFromBottom()
    }
  }

  /** 命中传统滚动条区域后，以后续 scroll 位置判断用户是否脱离或重新贴底。 */
  function handlePointerDown(event: PointerEvent) {
    const container = options.scrollContainerRef.value
    if (!container || event.target !== container) {
      return
    }
    const scrollbarWidth = container.offsetWidth - container.clientWidth
    const rect = container.getBoundingClientRect()
    if (scrollbarWidth > 0 && event.clientX >= rect.right - scrollbarWidth) {
      scrollbarDragging = true
      markUserScrollIntent('scrollbar')
    }
  }

  function releaseScrollbarDrag() {
    scrollbarDragging = false
  }

  /** 只有带用户意图的滚动才能改变跟随状态，内容增长和程序写入不会误切换。 */
  function handleScroll() {
    const container = options.scrollContainerRef.value
    const direction = currentUserScrollDirection()
    if (!container || !direction) {
      return
    }
    if (direction === 'up') {
      followingBottom.value = false
      return
    }
    const distanceToBottom = container.scrollHeight - container.scrollTop - container.clientHeight
    if (distanceToBottom <= ATTACH_BOTTOM_DISTANCE_PX) {
      followingBottom.value = true
      return
    }
    followingBottom.value = false
  }

  /** 把 watcher、ResizeObserver 等来源统一合并为每帧最多一次贴底写入。 */
  function scheduleScrollToBottom() {
    if (!followingBottom.value || nextTickPending || scrollAnimationFrame !== null) {
      return
    }
    nextTickPending = true
    void nextTick(() => {
      nextTickPending = false
      if (!followingBottom.value || scrollAnimationFrame !== null) {
        return
      }
      scrollAnimationFrame = window.requestAnimationFrame(() => {
        scrollAnimationFrame = null
        const container = options.scrollContainerRef.value
        if (!container || !followingBottom.value) {
          return
        }
        container.scrollTop = Math.max(0, container.scrollHeight - container.clientHeight)
      })
    })
  }

  /** 新会话默认展示最新消息，不继承上一会话的历史阅读位置。 */
  watch(options.sessionKey, () => {
    followingBottom.value = true
    userScrollIntentUntil = 0
    userScrollDirection = null
    scheduleScrollToBottom()
  }, { flush: 'post' })

  onMounted(() => {
    if (typeof ResizeObserver !== 'undefined' && options.scrollContentRef.value) {
      contentResizeObserver = new ResizeObserver(scheduleScrollToBottom)
      contentResizeObserver.observe(options.scrollContentRef.value)
    }
    window.addEventListener('pointerup', releaseScrollbarDrag)
    window.addEventListener('pointercancel', releaseScrollbarDrag)
    scheduleScrollToBottom()
  })

  onBeforeUnmount(() => {
    contentResizeObserver?.disconnect()
    window.removeEventListener('pointerup', releaseScrollbarDrag)
    window.removeEventListener('pointercancel', releaseScrollbarDrag)
    if (scrollAnimationFrame !== null) {
      window.cancelAnimationFrame(scrollAnimationFrame)
    }
  })

  return {
    handleKeydown,
    handlePointerDown,
    handleScroll,
    handleTouchEnd,
    handleTouchMove,
    handleTouchStart,
    handleWheel,
    scheduleScrollToBottom,
  }
}
