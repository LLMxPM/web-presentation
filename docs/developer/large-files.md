# 大文件与媒体资产管理

仓库使用 Git LFS 管理视频、无损音频和设计源文件，避免大型二进制内容进入普通 Git 历史。具体扩展名以根目录 [`.gitattributes`](../../.gitattributes) 为准。

## 首次准备

安装 Git LFS 后，在仓库内执行：

```powershell
git lfs install
git lfs pull
```

Git LFS 配置由 `.gitattributes` 自动生效。克隆仓库后执行 `git lfs pull`，可补齐尚未下载的媒体内容。

## 添加与检查

常见视频、无损音频和设计源文件可以正常使用 `git add`；Git 会在提交时保存 LFS 指针，并将文件内容交给 LFS 存储。提交前建议检查：

```powershell
git check-attr filter -- docs/assets/平台演示.mp4
git lfs status
```

第一条命令应输出 `filter: lfs`。暂存后，`git lfs status` 应列出对应文件。

对于 `.gitattributes` 尚未覆盖且大于 10 MiB 的二进制文件，应先评估是否确有入库必要；需要入库时，使用精确路径添加 LFS 规则：

```powershell
git lfs track "path/to/large-file.ext"
git add .gitattributes "path/to/large-file.ext"
```

不要把依赖包、构建产物、缓存、临时导出文件或可重新生成的文件提交到仓库；此类内容应加入 `.gitignore` 或交由发布制品存储管理。

## 调整已有文件

不要直接对共享分支执行 `git lfs migrate import`，该命令会重写 Git 历史。历史文件需要迁移时，应先评估远端、分支和协作者影响，再在独立维护窗口执行并通知所有协作者重新同步。
