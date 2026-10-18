/**
 * 文件功能：验证键盘注册表的上下文隔离、修饰键策略与键名归一化。
 */
import { describe, expect, it } from 'vitest'

import {
  isEditableKeyboardTarget,
  normalizeKeyboardKey,
  resolveKeyboardCommand,
} from './keyboard-map'
import type { KeyboardContext } from './keyboard-map'

/** 构造键盘事件，默认不带任何修饰键。 */
function keydown(key: string, init: KeyboardEventInit = {}): KeyboardEvent {
  return new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init })
}

/** 断言事件在指定上下文解析为给定动作。 */
function expectAction(key: string, context: KeyboardContext, action: string, init: KeyboardEventInit = {}): void {
  expect(resolveKeyboardCommand(keydown(key, init), context)?.action).toBe(action)
}

describe('keyboard-map', () => {
  it('预览态覆盖方向键、上下键、翻页键与空格', () => {
    for (const key of ['ArrowRight', 'ArrowDown', 'PageDown', ' ']) {
      expectAction(key, 'preview', 'next-page')
    }
    for (const key of ['ArrowLeft', 'ArrowUp', 'PageUp']) {
      expectAction(key, 'preview', 'previous-page')
    }
  })

  it('放映态空格与上下键同样翻页，不再切换自动/手动', () => {
    expectAction(' ', 'slideshow', 'next-page')
    expectAction('ArrowDown', 'slideshow', 'next-page')
    expectAction('ArrowUp', 'slideshow', 'previous-page')
  })

  it('卡片模式只保留翻页与关闭', () => {
    expectAction('ArrowRight', 'cards', 'next-page')
    expectAction('Escape', 'cards', 'close-card-mode')
    expect(resolveKeyboardCommand(keydown('Home'), 'cards')).toBeNull()
    expect(resolveKeyboardCommand(keydown('3'), 'cards')).toBeNull()
    expect(resolveKeyboardCommand(keydown('o'), 'cards')).toBeNull()
    expect(resolveKeyboardCommand(keydown('f'), 'cards')).toBeNull()
  })

  it('Home/End 只在预览与放映生效', () => {
    expectAction('Home', 'preview', 'first-page')
    expectAction('End', 'slideshow', 'last-page')
    expect(resolveKeyboardCommand(keydown('End'), 'cards')).toBeNull()
  })

  it('数字键返回目标页码，0 只用于两位数缓冲', () => {
    expect(resolveKeyboardCommand(keydown('7'), 'preview')).toEqual({ action: 'goto-page', pageNumber: 7 })
    expect(resolveKeyboardCommand(keydown('7'), 'slideshow')).toEqual({ action: 'goto-page', pageNumber: 7 })
    expect(resolveKeyboardCommand(keydown('0'), 'preview')).toEqual({ action: 'goto-page', pageNumber: 0 })
    expect(resolveKeyboardCommand(keydown('0'), 'slideshow')).toEqual({ action: 'goto-page', pageNumber: 0 })
  })

  it('O/F 仅在预览生效，F 不会在放映态重复进入', () => {
    expectAction('o', 'preview', 'open-card-mode')
    expectAction('f', 'preview', 'enter-slideshow')
    expect(resolveKeyboardCommand(keydown('o'), 'slideshow')).toBeNull()
    expect(resolveKeyboardCommand(keydown('f'), 'slideshow')).toBeNull()
  })

  it('Shift+P 打开演讲，单独 P 不触发', () => {
    expectAction('P', 'preview', 'open-presenter', { shiftKey: true })
    expectAction('p', 'slideshow', 'open-presenter', { shiftKey: true })
    expect(resolveKeyboardCommand(keydown('p'), 'preview')).toBeNull()
  })

  it('带 Ctrl/Meta/Alt 的组合一律不参与映射', () => {
    expect(resolveKeyboardCommand(keydown('ArrowRight', { ctrlKey: true }), 'preview')).toBeNull()
    expect(resolveKeyboardCommand(keydown('f', { metaKey: true }), 'preview')).toBeNull()
    expect(resolveKeyboardCommand(keydown(' ', { altKey: true }), 'slideshow')).toBeNull()
  })

  it('键名归一化覆盖空格别名与大小写', () => {
    expect(normalizeKeyboardKey(' ')).toBe('space')
    expect(normalizeKeyboardKey('Spacebar')).toBe('space')
    expect(normalizeKeyboardKey('ArrowRight')).toBe('arrowright')
    expect(normalizeKeyboardKey('P')).toBe('p')
  })

  it('可编辑区域判定覆盖输入类元素', () => {
    const input = document.createElement('input')
    const textarea = document.createElement('textarea')
    const select = document.createElement('select')
    const editable = document.createElement('div')
    // jsdom 不实现 isContentEditable，直接定义该属性以覆盖判定分支。
    Object.defineProperty(editable, 'isContentEditable', { value: true })
    const plain = document.createElement('div')

    expect(isEditableKeyboardTarget(input)).toBe(true)
    expect(isEditableKeyboardTarget(textarea)).toBe(true)
    expect(isEditableKeyboardTarget(select)).toBe(true)
    expect(isEditableKeyboardTarget(editable)).toBe(true)
    expect(isEditableKeyboardTarget(plain)).toBe(false)
    expect(isEditableKeyboardTarget(null)).toBe(false)
  })
})
