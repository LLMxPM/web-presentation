# 项目模板包 v1

项目模板包用于把一个项目作为完整快照导出，并在其它工作空间导入为新项目。模板库网站不放在 `web-presentation` 仓库内；外部模板库只需要保存 `.wptemplate.zip` 原包，并读取包内元数据与截图进行展示。

## 包格式

模板包是 ZIP 文件，建议扩展名使用 `.wptemplate.zip`。v1 根结构如下：

```text
manifest.json
metadata/template.json
metadata/screenshots.json
screenshots/cover.png
screenshots/pages/<source_page_code>.png
project/project.json
project/routes.json
pages/<source_page_code>/page.json
pages/<source_page_code>/index.vue
components/<source_component_code>/component.json
components/<source_component_code>/index.vue
components/<source_component_code>/preview.schema.json
themes/<theme_key>.json
assets/<file_hash>/asset.json
assets/<file_hash>/<original_name>
fonts/font-configs.json
```

`manifest.json` 必须包含：

- `package_type`: 固定为 `web-presentation-project-template`
- `schema_version`: v1 固定为 `1`
- `template_path`: 固定为 `metadata/template.json`
- `screenshots_path`: 固定为 `metadata/screenshots.json`
- `project_path`: 固定为 `project/project.json`
- `routes_path`: 固定为 `project/routes.json`
- `page_count`、`component_count`、`asset_count`、`theme_count`、`font_count`

`metadata/template.json` 面向模板库展示，稳定字段包括 `slug`、`name`、`summary`、`description`、`author`、`page_count`、`page_width`、`page_height`、`aspect_ratio`、`runtime_kit_manifest_version`、`created_at`、`updated_at`。其中 `author` 由导出时的当前用户显示名称生成。当前项目模型没有维护 `language`、`license`、`content_types`、`style_keywords`、`category`、`tags`，导出包不得写入这些推测字段。

`metadata/screenshots.json` 面向模板库详情页展示，包含 `cover` 和 `pages`。截图路径必须指向包内 `screenshots/` 目录下的实际文件。

## Backend API

- `POST /api/projects/{project_id}/template-package/export/validate`
- `POST /api/projects/{project_id}/template-package/export`
- `POST /api/workspaces/{workspace_id}/template-packages/import/validate`
- `POST /api/workspaces/{workspace_id}/template-packages/import`
- `POST /api/workspaces/{workspace_id}/template-packages/preview-artifact`

导出接口会收集项目配置、路由、页面源码、组件依赖闭包、资源、主题、字体配置、项目建议组件和建议资源。导入接口总是创建新项目，并按目标工作空间现有规则复用或阻断组件、资源、主题和字体冲突。

## 外部模板库约定

模板库网站保存 `.wptemplate.zip` 原包。列表卡片读取 `metadata/template.json` 和 `screenshots/cover.png`，详情页读取 `metadata/screenshots.json` 展示页面截图。用户下载归档文件后，通过 Editor 的“导入项目”入口导入。
