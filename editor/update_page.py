import re
import os

file_path = r'c:\code\web-presentation\editor\src\views\PageDetailView.vue'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add History Button to Toolbar
toolbar_btn_target = """<div class="flex items-center gap-2">
            <BaseButton variant="ghost" size="sm" :class="themeClasses.button" @click="copyCode">"""
toolbar_btn_repl = """<div class="flex items-center gap-2">
            <BaseButton variant="ghost" size="sm" :class="themeClasses.button" @click="isHistoryModalOpen = true">
              <History class="w-3.5 h-3.5" />
              版本历史
            </BaseButton>
            <BaseButton variant="ghost" size="sm" :class="themeClasses.button" @click="copyCode">"""
content = content.replace(toolbar_btn_target, toolbar_btn_repl)

# 2. Add Flex Wrapper around Editor 
editor_wrapper_target = """      </div>

      <div class="card overflow-hidden shadow-2xl transition-all duration-300 ring-1" :class="themeClasses.card">"""
editor_wrapper_repl = """      </div>

      <div class="flex flex-col lg:flex-row gap-6 items-start">
        <div class="card overflow-hidden shadow-2xl transition-all duration-300 ring-1 flex-1 w-full min-w-0" :class="themeClasses.card">"""
content = content.replace(editor_wrapper_target, editor_wrapper_repl)

# 3. Modify Preview Layout & Iframe Aspect Ratio
preview_target = """<section v-if="previewUrl" class="space-y-3">"""
preview_repl = """<section v-if="previewUrl" class="w-full lg:w-[45%] xl:w-[50%] shrink-0 space-y-3 sticky top-6">"""
content = content.replace(preview_target, preview_repl)

iframe_target = """<iframe :src="previewFrameUrl" title="runtime-preview" class="block w-full aspect-video bg-slate-50"
            referrerpolicy="same-origin" />"""
iframe_repl = """<iframe :src="previewFrameUrl" title="runtime-preview" class="block w-full bg-slate-50 min-h-[500px] lg:h-[min(68vh,760px)]"
            referrerpolicy="same-origin" />"""
content = content.replace(iframe_target, iframe_repl)

# 4. Extract History Section and place it inside BaseDialog
pattern = re.compile(r'(<section class="rounded-3xl border border-slate-200 bg-white/95 shadow-sm backdrop-blur">.*?</section>)', re.DOTALL)
match = pattern.search(content)

if match:
    history_html = match.group(1)
    
    # modify history_html to BaseDialog
    history_html = history_html.replace('<section class="rounded-3xl border border-slate-200 bg-white/95 shadow-sm backdrop-blur">', '<BaseDialog v-model="isHistoryModalOpen" title="版本历史" width="1000px">')
    history_html = history_html.replace('</section>', '</BaseDialog>')
    
    # remove padding from history header since dialog has padding
    history_html = history_html.replace('<div class="flex items-center justify-between gap-4 px-6 py-5 border-b border-slate-100 flex-wrap">', '<div class="flex items-center justify-between gap-4 py-3 border-b border-slate-100 flex-wrap">')
    
    # Remove it from its original place
    content = content[:match.start(1)] + content[match.end(1):]
    
    # Now we need to insert history_html AT THE END of the v-else-if="pageDetails" block
    # Note: we need to close the flex wrapper first.
    # The block ends with the preview section, then it goes to: </div>\n    <div v-else class="flex flex-col...
    insert_pattern = re.compile(r'(\n    </div>\n\n    <div v-else class="flex flex-col items-center justify-center min-h-\[60vh\] gap-8">)')
    
    match2 = insert_pattern.search(content)
    if match2:
        content = content[:match2.start(1)] + '\n      </div>\n' + history_html + match2.group(1) + content[match2.end(1):]


# 5. Remove unused import of `getDefaultEditorTheme`
content = content.replace("import { getDefaultEditorTheme } from '@/utils/monaco'\n", "")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated PageDetailView.vue successfully.')
