/**
 * 文件功能：验证 MonacoCodeEditor 的自动保存、快捷键和脏状态重置行为。
 */
import { nextTick } from 'vue'
import { render } from '@testing-library/vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/monaco', () => {
  class FakeDisposable {
    dispose = vi.fn()
  }

  class FakeModel {
    value: string
    uri: { toString: () => string }
    dispose = vi.fn()

    constructor(value: string, uri: { toString: () => string }) {
      this.value = value
      this.uri = uri
    }

    setValue(nextValue: string) {
      this.value = nextValue
    }
  }

  class FakeEditor {
    model: FakeModel
    changeHandlers: Array<() => void> = []
    actions = new Map<string, { run: () => void | Promise<void> }>()
    dispose = vi.fn()
    focus = vi.fn()
    updateOptions = vi.fn()

    constructor(model: FakeModel) {
      this.model = model
    }

    onDidChangeModelContent(handler: () => void) {
      this.changeHandlers.push(handler)
      return new FakeDisposable()
    }

    addAction(action: { id: string; run: () => void | Promise<void> }) {
      this.actions.set(action.id, action)
      return {
        dispose: vi.fn(() => {
          this.actions.delete(action.id)
        }),
      }
    }

    getValue() {
      return this.model.value
    }

    getModel() {
      return this.model
    }

    triggerChange(nextValue: string) {
      this.model.value = nextValue
      this.changeHandlers.forEach(handler => handler())
    }

    async triggerAction(actionId: string) {
      await this.actions.get(actionId)?.run()
    }
  }

  const state = {
    createdEditors: [] as FakeEditor[],
    registerCompletionItemProvider: vi.fn(() => new FakeDisposable()),
    setModelLanguage: vi.fn(),
    setTheme: vi.fn(),
  }

  ;(globalThis as typeof globalThis & { __monacoMockState?: typeof state }).__monacoMockState = state

  const fakeMonaco = {
    editor: {
      create: (_container: HTMLElement, options: { model: FakeModel }) => {
        const editor = new FakeEditor(options.model)
        state.createdEditors.push(editor)
        return editor
      },
      createModel: (value: string, _language: string, uri: { toString: () => string }) => new FakeModel(value, uri),
      setModelLanguage: state.setModelLanguage,
      defineTheme: vi.fn(),
      setTheme: state.setTheme,
    },
    languages: {
      registerCompletionItemProvider: state.registerCompletionItemProvider,
      CompletionItemInsertTextRule: {
        InsertAsSnippet: 4,
        None: 0,
      },
      CompletionItemKind: {
        Snippet: 27,
        Keyword: 17,
        Function: 1,
        Property: 10,
        Text: 18,
      },
    },
    Uri: {
      parse: (value: string) => ({ toString: () => value }),
    },
    KeyMod: {
      CtrlCmd: 2048,
    },
    KeyCode: {
      KeyS: 49,
    },
  }

  return {
    __monacoMockState: state,
    MonacoKeyMod: fakeMonaco.KeyMod,
    MonacoKeyCode: fakeMonaco.KeyCode,
    getDefaultEditorOptions: () => ({}),
    getDefaultEditorTheme: () => 'dark',
    initializeMonaco: vi.fn(async () => fakeMonaco),
    resolveCompletionSuggestions: vi.fn(() => [
      { label: 'vue-sfc', insertText: '<template />', kind: 'Snippet', insertTextRules: 'snippet' },
    ]),
    resolveMonacoLanguage: vi.fn((language: string) => (language === 'vue' ? 'html' : language)),
    resolveMonacoTheme: vi.fn((mode: string) => mode),
    toMonacoCompletionItems: vi.fn((suggestions: unknown[]) => suggestions),
  }
})

import MonacoCodeEditor from '@/components/editor/MonacoCodeEditor.vue'

function getMonacoMockState() {
  return (globalThis as typeof globalThis & {
    __monacoMockState: {
      createdEditors: Array<{
        triggerChange: (nextValue: string) => void
        triggerAction: (actionId: string) => Promise<void>
      }>
      registerCompletionItemProvider: ReturnType<typeof vi.fn>
      setModelLanguage: ReturnType<typeof vi.fn>
      setTheme: ReturnType<typeof vi.fn>
    }
  }).__monacoMockState
}

function getEmitted(view: ReturnType<typeof render>) {
  return view.emitted() as Record<string, Array<unknown[]>>
}

describe('MonacoCodeEditor', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    const monacoMockState = getMonacoMockState()
    monacoMockState.createdEditors.length = 0
    monacoMockState.registerCompletionItemProvider.mockClear()
    monacoMockState.setModelLanguage.mockClear()
    monacoMockState.setTheme.mockClear()
  })

  afterEach(() => {
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
  })

  it('应在内容变更后触发自动保存并更新脏状态', async () => {
    const view = render(MonacoCodeEditor, {
      props: {
        modelValue: '<template />',
        autoSaveDelay: 30,
      },
    })

    await nextTick()
    const monacoMockState = getMonacoMockState()
    monacoMockState.createdEditors[0].triggerChange('<template>\n  <div />\n</template>')
    const emitted = getEmitted(view)

    expect(emitted['update:modelValue']?.[0]?.[0]).toContain('<div />')
    expect(emitted['dirty-change']?.[0]?.[0]).toBe(true)

    vi.advanceTimersByTime(35)
    await nextTick()

    expect(getEmitted(view).save?.[0]?.[0]).toEqual({
      reason: 'auto',
      value: '<template>\n  <div />\n</template>',
    })
  })

  it('应响应 Ctrl/Cmd+S 并允许在保存后重置脏状态', async () => {
    const view = render(MonacoCodeEditor, {
      props: {
        modelValue: 'const title = "draft"',
        autoSaveDelay: 0,
      },
    })

    await nextTick()
    const monacoMockState = getMonacoMockState()
    monacoMockState.createdEditors[0].triggerChange('const title = "saved"')
    await monacoMockState.createdEditors[0].triggerAction('page-code-save')

    expect(getEmitted(view).save?.[0]?.[0]).toEqual({
      reason: 'manual',
      value: 'const title = "saved"',
    })

    const readyPayload = getEmitted(view).ready?.[0]?.[0] as { markClean: (value: string) => void }
    readyPayload.markClean('const title = "saved"')

    const dirtyEvents = getEmitted(view)['dirty-change'] ?? []
    expect(dirtyEvents[dirtyEvents.length - 1]?.[0]).toBe(false)
  })

  it('同页多个编辑器实例应创建不同的 Monaco model URI', async () => {
    render({
      components: { MonacoCodeEditor },
      template: `
        <div>
          <MonacoCodeEditor model-value="first" language="yaml" :auto-save-delay="0" />
          <MonacoCodeEditor model-value="second" language="yaml" :auto-save-delay="0" />
        </div>
      `,
    })

    await nextTick()

    const monacoMockState = getMonacoMockState()
    const modelUris = monacoMockState.createdEditors.map((editor: any) => editor.model.uri.toString())

    expect(modelUris).toHaveLength(2)
    expect(new Set(modelUris).size).toBe(2)
  })
})
