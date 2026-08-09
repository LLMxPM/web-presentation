"""文件功能：承载 catalog components 场景的拆分测试用例。"""

from __future__ import annotations

from tests.api.catalog.catalog_cases import *  # noqa: F403


async def test_workspace_component_should_persist_component_type_and_support_filter(authenticated_client: AsyncClient) -> None:
    """工作空间组件应保存 component_type，并支持列表过滤与更新。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "组件类型工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "统计卡片",
            "import_name": "StatsCard",
            "content": "<template><div>card</div></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "summary": "展示统计信息",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component_data = create_response.json()
    assert component_data["component_type"] == "内容组件"
    assert component_data["import_name"] == "StatsCard"

    update_response = await authenticated_client.patch(
        f"/api/components/{component_data['id']}",
        json={
            "import_name": "StatsResourceCard",
            "component_type": "原子组件",
            "change_note": "补充组件类型",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["component_type"] == "原子组件"
    assert update_response.json()["import_name"] == "StatsResourceCard"

    filtered_response = await authenticated_client.get(
        "/api/components",
        params={"workspace_id": workspace_id, "component_type": "原子组件"},
    )
    assert filtered_response.status_code == 200
    assert filtered_response.json()["items"][0]["component_type"] == "原子组件"
    assert filtered_response.json()["items"][0]["import_name"] == "StatsResourceCard"

async def test_workspace_component_list_should_support_published_only_filter(authenticated_client: AsyncClient) -> None:
    """工作空间组件列表应支持只返回已有正式版本的组件，供只读侧栏引用。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "组件发布过滤工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    published_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "已发布侧栏组件",
            "import_name": "PublishedSidebarComponent",
            "content": "<template><div>published</div></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert published_response.status_code == 200
    draft_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "未发布侧栏组件",
            "import_name": "DraftSidebarComponent",
            "content": "<template><div>draft</div></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert draft_response.status_code == 200

    publish_response = await authenticated_client.post(
        f"/api/components/{published_response.json()['id']}/publish",
        json={"release_name": "侧栏可引用版本"},
    )
    assert publish_response.status_code == 200

    filtered_response = await authenticated_client.get(
        "/api/components",
        params={"workspace_id": workspace_id, "published_only": "true"},
    )
    assert filtered_response.status_code == 200
    filtered_data = filtered_response.json()
    assert filtered_data["total"] == 1
    assert {item["name"] for item in filtered_data["items"]} == {"已发布侧栏组件"}
    assert all(item["current_version_no"] > 0 for item in filtered_data["items"])

async def test_workspace_component_import_name_should_be_required_valid_and_unique(authenticated_client: AsyncClient) -> None:
    """工作空间组件引用名应必填、符合 PascalCase，并在同一工作空间启用组件内唯一。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "组件引用名工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    missing_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "缺少引用名组件",
            "content": "<template><div>missing</div></template>",
            "file_type": "vue",
            "status": "active",
        },
    )
    assert missing_response.status_code == 422

    invalid_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "非法引用名组件",
            "import_name": "stats-card",
            "content": "<template><div>invalid</div></template>",
            "file_type": "vue",
            "status": "active",
        },
    )
    assert invalid_response.status_code == 422

    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "统计卡片",
            "import_name": "StatsCard",
            "content": "<template><div>card</div></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200

    duplicate_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "重复统计卡片",
            "import_name": "StatsCard",
            "content": "<template><div>duplicate</div></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["code"] == "COMPONENT_IMPORT_NAME_CONFLICT"

    archived_duplicate_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "归档重复统计卡片",
            "import_name": "StatsCard",
            "content": "<template><div>archived</div></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "archived",
        },
    )
    assert archived_duplicate_response.status_code == 200

async def test_workspace_component_should_reject_unknown_component_type(authenticated_client: AsyncClient) -> None:
    """工作空间组件仅允许使用固定组件分类。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "固定组件分类工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200

    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_response.json()["id"],
            "name": "自由分类组件",
            "import_name": "FreeCategoryComponent",
            "content": "<template><div>demo</div></template>",
            "file_type": "vue",
            "component_type": "card",
            "status": "active",
        },
    )
    assert create_response.status_code == 422
    assert create_response.json()["code"] == "VALIDATION_ERROR"
    assert "component_type" in create_response.json()["message"]

    legacy_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_response.json()["id"],
            "name": "旧分类组件",
            "import_name": "LegacyCategoryComponent",
            "content": "<template><div>legacy</div></template>",
            "file_type": "vue",
            "component_type": "内容区块",
            "status": "active",
        },
    )
    assert legacy_response.status_code == 422
    assert legacy_response.json()["code"] == "VALIDATION_ERROR"
    assert "component_type" in legacy_response.json()["message"]

async def test_content_component_should_require_size_control_preview_schema(authenticated_client: AsyncClient) -> None:
    """所有组件必须配置 previewSchema，且内容组件必须声明尺寸控制参数。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "内容组件尺寸校验工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    missing_schema_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "缺少尺寸的内容组件",
            "import_name": "MissingSizeContentComponent",
            "content": "<template><section>missing-size</section></template>",
            "file_type": "vue",
            "component_type": "内容组件",
            "status": "active",
        },
    )
    assert missing_schema_response.status_code == 400
    assert missing_schema_response.json()["code"] == "CONTENT_COMPONENT_SIZE_CONTROL_REQUIRED"

    missing_size_prop_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "无尺寸参数内容组件",
            "import_name": "NoSizePropContentComponent",
            "content": "<template><section>no-size-prop</section></template>",
            "preview_schema": '{"props":{"title":{"type":"string","label":"标题","default":"示例"}}}',
            "file_type": "vue",
            "component_type": "内容组件",
            "status": "active",
        },
    )
    assert missing_size_prop_response.status_code == 400
    assert missing_size_prop_response.json()["code"] == "CONTENT_COMPONENT_SIZE_CONTROL_REQUIRED"

    for component_type, import_name in (("页面组件", "MissingPageSchema"), ("原子组件", "MissingAtomicSchema")):
        missing_other_schema_response = await authenticated_client.post(
            "/api/components",
            json={
                "workspace_id": workspace_id,
                "name": f"缺少 Schema 的{component_type}",
                "import_name": import_name,
                "content": "<template><span>missing schema</span></template>",
                "file_type": "vue",
                "component_type": component_type,
                "status": "active",
            },
        )
        assert missing_other_schema_response.status_code == 400
        assert missing_other_schema_response.json()["code"] == "COMPONENT_PREVIEW_SCHEMA_REQUIRED"

    atomic_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "页码原子组件",
            "import_name": "PageNumberAtom",
            "content": "<template><span>1</span></template>",
            "preview_schema": '{"props":{"value":{"type":"number","label":"页码","default":1}}}',
            "file_type": "vue",
            "component_type": "原子组件",
            "status": "active",
        },
    )
    assert atomic_response.status_code == 200

    update_response = await authenticated_client.patch(
        f"/api/components/{atomic_response.json()['id']}",
        json={"component_type": "内容组件", "change_note": "切换为内容组件"},
    )
    assert update_response.status_code == 400
    assert update_response.json()["code"] == "CONTENT_COMPONENT_SIZE_CONTROL_REQUIRED"

async def test_component_package_import_should_return_imported_components(authenticated_client: AsyncClient) -> None:
    """组件分享包导入后应直接返回已导入组件，不能触发异步 ORM 隐式加载。"""

    source_workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "组件导出工作空间", "status": "active"},
    )
    assert source_workspace_response.status_code == 200
    source_workspace_id = source_workspace_response.json()["id"]
    target_workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "组件导入工作空间", "status": "active"},
    )
    assert target_workspace_response.status_code == 200
    target_workspace_id = target_workspace_response.json()["id"]

    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": source_workspace_id,
            "name": "导出卡片",
            "import_name": "ExportedCard",
            "component_type": "内容组件",
            "content": "<template><section>exported</section></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component_id = create_response.json()["id"]
    publish_response = await authenticated_client.post(
        f"/api/components/{component_id}/publish",
        json={"release_name": "导出版"},
    )
    assert publish_response.status_code == 200

    export_response = await authenticated_client.post(
        "/api/components/export-package",
        json={"workspace_id": source_workspace_id, "component_ids": [component_id]},
    )
    assert export_response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(export_response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        component_payload = json.loads(archive.read(f"components/{publish_response.json()['code']}/component.json").decode("utf-8"))
        assert manifest["schema_version"] == 2
        assert isinstance(manifest["components"][0]["component_fingerprint"], str)
        assert isinstance(component_payload["component_fingerprint"], str)
        assert component_payload["fingerprint_schema_version"] == 1

    import_response = await authenticated_client.post(
        "/api/components/import-package",
        data={"workspace_id": str(target_workspace_id)},
        files={"archive": ("components.zip", export_response.content, "application/zip")},
    )
    assert import_response.status_code == 200
    imported_components = import_response.json()["imported_components"]
    assert len(imported_components) == 1
    assert imported_components[0]["workspace_id"] == target_workspace_id
    assert imported_components[0]["name"] == "导出卡片"
    assert imported_components[0]["import_name"] == "ExportedCard"
    assert imported_components[0]["component_type"] == "内容组件"
    assert imported_components[0]["current_version_no"] == 1
    assert import_response.json()["components"][0]["action"] == "create"
    async with get_session_factory()() as session:
        version = await session.scalar(
            select(WorkspaceComponentVersion)
            .join(WorkspaceComponent, WorkspaceComponent.id == WorkspaceComponentVersion.component_id)
            .where(WorkspaceComponent.id == imported_components[0]["id"])
            .where(WorkspaceComponentVersion.version_no == WorkspaceComponent.current_version_no)
        )
        assert version is not None
        version.content_hash = None
        version.preview_schema_hash = None
        version.component_fingerprint = None
        version.fingerprint_schema_version = None
        await session.commit()

    reuse_validation_response = await authenticated_client.post(
        "/api/components/import-package/validate",
        data={"workspace_id": str(target_workspace_id)},
        files={"archive": ("components.zip", export_response.content, "application/zip")},
    )
    assert reuse_validation_response.status_code == 200
    assert reuse_validation_response.json()["valid"] is True
    assert reuse_validation_response.json()["components"][0]["action"] == "reuse"

    reuse_import_response = await authenticated_client.post(
        "/api/components/import-package",
        data={"workspace_id": str(target_workspace_id)},
        files={"archive": ("components.zip", export_response.content, "application/zip")},
    )
    assert reuse_import_response.status_code == 200
    assert reuse_import_response.json()["imported_components"] == []
    assert reuse_import_response.json()["components"][0]["action"] == "reuse"

async def test_component_package_export_should_warn_and_allow_manual_assets(authenticated_client: AsyncClient) -> None:
    """组件包导出遇到动态资源和缺失静态资源时应 warning，可手动补充资源。"""

    source_workspace = await _create_catalog_workspace(authenticated_client, "组件动态资源源空间")
    target_workspace = await _create_catalog_workspace(authenticated_client, "组件动态资源目标空间")
    static_asset = await _create_catalog_svg_asset(authenticated_client, source_workspace["id"], "share_static_logo")
    missing_asset = await _create_catalog_svg_asset(authenticated_client, source_workspace["id"], "share_missing_logo")
    manual_asset = await _create_catalog_svg_asset(authenticated_client, source_workspace["id"], "share_manual_photo")
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": source_workspace["id"],
            "name": "动态资源卡片",
            "import_name": "DynamicAssetCard",
            "component_type": "内容组件",
            "content": (
                "<template>"
                '<AssetImage name="share_static_logo" />'
                '<AssetImage name="share_missing_logo" />'
                '<AssetImage :name="props.runtimeAssetName" />'
                "</template>"
                "<script setup>const props = defineProps({ runtimeAssetName: String })</script>"
            ),
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component_id = create_response.json()["id"]
    publish_response = await authenticated_client.post(
        f"/api/components/{component_id}/publish",
        json={"release_name": "动态资源导出版"},
    )
    assert publish_response.status_code == 200

    archive_response = await authenticated_client.post(
        f"/api/workspaces/{source_workspace['id']}/assets/{missing_asset['id']}/archive",
        json={"archive_reason": "测试缺失静态资源 warning"},
    )
    assert archive_response.status_code == 200

    validate_response = await authenticated_client.post(
        "/api/components/export-package/validate",
        json={
            "workspace_id": source_workspace["id"],
            "component_ids": [component_id],
            "manual_asset_names": ["share_manual_photo", "not_exists"],
        },
    )
    assert validate_response.status_code == 200, validate_response.json()
    validation = validate_response.json()
    assert validation["can_export"] is True
    assert validation["dynamic_resource_components"] == ["动态资源卡片"]
    assert validation["missing_static_asset_names"] == ["share_missing_logo"]
    assert validation["missing_manual_asset_names"] == ["not_exists"]
    assert {item["name"] for item in validation["automatic_assets"]} == {"share_static_logo"}
    assert {item["name"] for item in validation["manual_assets"]} == {"share_manual_photo"}

    export_response = await authenticated_client.post(
        "/api/components/export-package",
        json={
            "workspace_id": source_workspace["id"],
            "component_ids": [component_id],
            "manual_asset_names": ["share_manual_photo", "not_exists"],
        },
    )
    assert export_response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(export_response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        component_payload = json.loads(archive.read(f"components/{publish_response.json()['code']}/component.json").decode("utf-8"))
        assert manifest["export_warnings"]
        assert manifest["manual_asset_names"] == ["share_manual_photo"]
        assert manifest["missing_asset_names"] == ["share_missing_logo", "not_exists"]
        assert manifest["dynamic_resource_components"] == ["动态资源卡片"]
        assert {item["name"] for item in manifest["assets"]} == {"share_static_logo", "share_manual_photo"}
        assert component_payload["asset_names"] == ["share_static_logo"]
        assert "share_manual_photo" not in component_payload["asset_names"]
        assert f"assets/{static_asset['file_hash']}/asset.json" in archive.namelist()
        assert f"assets/{manual_asset['file_hash']}/asset.json" in archive.namelist()

    import_validation_response = await authenticated_client.post(
        "/api/components/import-package/validate",
        data={"workspace_id": str(target_workspace["id"])},
        files={"archive": ("components.zip", export_response.content, "application/zip")},
    )
    assert import_validation_response.status_code == 200
    import_validation = import_validation_response.json()
    assert import_validation["valid"] is True
    assert import_validation["warnings"] == manifest["export_warnings"]

    import_response = await authenticated_client.post(
        "/api/components/import-package",
        data={"workspace_id": str(target_workspace["id"])},
        files={"archive": ("components.zip", export_response.content, "application/zip")},
    )
    assert import_response.status_code == 200
    assert import_response.json()["warnings"] == manifest["export_warnings"]
    assert import_response.json()["components"][0]["action"] == "create"

async def test_component_package_import_should_reject_legacy_schema_and_tampered_fingerprint(
    authenticated_client: AsyncClient,
) -> None:
    """组件分享包应拒绝旧 schema 和被篡改的组件指纹。"""

    workspace = await _create_catalog_workspace(authenticated_client, "组件指纹源空间")
    target = await _create_catalog_workspace(authenticated_client, "组件指纹目标空间")
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace["id"],
            "name": "指纹卡片",
            "import_name": "FingerprintCard",
            "component_type": "内容组件",
            "content": "<template><section>fingerprint</section></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component_id = create_response.json()["id"]
    publish_response = await authenticated_client.post(
        f"/api/components/{component_id}/publish",
        json={"release_name": "导出版"},
    )
    assert publish_response.status_code == 200
    export_response = await authenticated_client.post(
        "/api/components/export-package",
        json={"workspace_id": workspace["id"], "component_ids": [component_id]},
    )
    assert export_response.status_code == 200

    legacy_archive = _rewrite_zip_json(export_response.content, "manifest.json", lambda payload: {**payload, "schema_version": 1})
    legacy_response = await authenticated_client.post(
        "/api/components/import-package/validate",
        data={"workspace_id": str(target["id"])},
        files={"archive": ("components.zip", legacy_archive, "application/zip")},
    )
    assert legacy_response.status_code == 200
    assert legacy_response.json()["valid"] is False
    assert any("schema_version" in error for error in legacy_response.json()["errors"])

    component_code = publish_response.json()["code"]
    tampered_archive = _rewrite_zip_json(
        export_response.content,
        f"components/{component_code}/component.json",
        lambda payload: {**payload, "component_fingerprint": "0" * 64},
    )
    tampered_response = await authenticated_client.post(
        "/api/components/import-package/validate",
        data={"workspace_id": str(target["id"])},
        files={"archive": ("components.zip", tampered_archive, "application/zip")},
    )
    assert tampered_response.status_code == 200
    assert tampered_response.json()["valid"] is False
    assert any("component_fingerprint" in error for error in tampered_response.json()["errors"])


async def test_workspace_component_archive_and_restore_round_trip(authenticated_client: AsyncClient) -> None:
    """组件归档后退出普通列表并可恢复，恢复前校验引用名未被启用组件占用。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "组件归档恢复工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "可恢复组件",
            "import_name": "RestorableCard",
            "content": "<template><div>restorable</div></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component_id = create_response.json()["id"]

    active_list = await authenticated_client.get(
        "/api/components",
        params={"workspace_id": workspace_id},
    )
    assert active_list.status_code == 200
    assert active_list.json()["total"] == 1

    archive_response = await authenticated_client.post(f"/api/components/{component_id}/archive")
    assert archive_response.status_code == 200

    active_after_archive = await authenticated_client.get(
        "/api/components",
        params={"workspace_id": workspace_id},
    )
    assert active_after_archive.status_code == 200
    assert active_after_archive.json()["total"] == 0

    archived_list = await authenticated_client.get(
        "/api/components",
        params={"workspace_id": workspace_id, "status": "archived"},
    )
    assert archived_list.status_code == 200
    assert archived_list.json()["total"] == 1
    assert archived_list.json()["items"][0]["status"] == "archived"

    detail_response = await authenticated_client.get(f"/api/components/{component_id}")
    assert detail_response.status_code == 404

    restore_response = await authenticated_client.post(f"/api/components/{component_id}/restore")
    assert restore_response.status_code == 200

    active_after_restore = await authenticated_client.get(
        "/api/components",
        params={"workspace_id": workspace_id},
    )
    assert active_after_restore.status_code == 200
    assert active_after_restore.json()["total"] == 1

    detail_after_restore = await authenticated_client.get(f"/api/components/{component_id}")
    assert detail_after_restore.status_code == 200
    assert detail_after_restore.json()["status"] == "active"

    # 再次恢复已启用组件应保持幂等，不报错。
    idempotent_restore = await authenticated_client.post(f"/api/components/{component_id}/restore")
    assert idempotent_restore.status_code == 200


async def test_workspace_component_restore_should_reject_conflicting_import_name(
    authenticated_client: AsyncClient,
) -> None:
    """恢复归档组件时，若其引用名已被新的启用组件占用，应返回引用名冲突错误。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "组件恢复冲突工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    async def _create_component(name: str, import_name: str, status: str) -> int:
        """创建组件草稿并返回组件 ID。"""

        create_response = await authenticated_client.post(
            "/api/components",
            json={
                "workspace_id": workspace_id,
                "name": name,
                "import_name": import_name,
                "content": "<template><div>conflict</div></template>",
                "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
                "file_type": "vue",
                "status": status,
            },
        )
        assert create_response.status_code == 200, create_response.text
        return int(create_response.json()["id"])

    original_id = await _create_component("原始组件", "TwinCard", "active")
    archive_response = await authenticated_client.post(f"/api/components/{original_id}/archive")
    assert archive_response.status_code == 200

    # 归档后引用名被释放，新启用组件可以复用。
    replacement_id = await _create_component("替换组件", "TwinCard", "active")

    restore_response = await authenticated_client.post(f"/api/components/{original_id}/restore")
    assert restore_response.status_code == 409
    assert restore_response.json()["code"] == "COMPONENT_IMPORT_NAME_CONFLICT"

    # 归档列表仍保留，未发生部分恢复。
    archived_list = await authenticated_client.get(
        "/api/components",
        params={"workspace_id": workspace_id, "status": "archived"},
    )
    assert archived_list.status_code == 200
    assert [item["id"] for item in archived_list.json()["items"]] == [original_id]

    active_list = await authenticated_client.get(
        "/api/components",
        params={"workspace_id": workspace_id},
    )
    assert active_list.status_code == 200
    assert [item["id"] for item in active_list.json()["items"]] == [replacement_id]
