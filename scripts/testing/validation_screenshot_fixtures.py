"""文件功能：构造截图收益验收固定页面集，素材仅用于隔离 E2E 工作空间。"""

import json
import struct
from pathlib import Path


def red_model_glb() -> bytes:
    """生成无光照红色三角面，便于验证三维资源确实进入 PNG。"""
    positions = struct.pack("<9f", 0, .85, 0, -.85, -.75, 0, .85, -.75, 0)
    model = {"asset": {"version": "2.0"}, "extensionsUsed": ["KHR_materials_unlit"],
        "buffers": [{"byteLength": len(positions)}], "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(positions)}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [-.85,-.75,0], "max": [.85,.85,0]}],
        "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [1,0,0,1], "metallicFactor": 0, "roughnessFactor": 1}, "extensions": {"KHR_materials_unlit": {}}}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "material": 0}]}],
        "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0}
    data = json.dumps(model, separators=(",", ":")).encode()
    data += b" " * (-len(data) % 4)
    return struct.pack("<III", 0x46546C67, 2, 28 + len(data) + len(positions)) + struct.pack("<II", len(data), 0x4E4F534A) + data + struct.pack("<II", len(positions), 0x004E4942) + positions


async def create_fixed_pages(client, workspace_id: int, *, request_json, root: Path, context_source: str) -> dict[str, str]:
    """创建真实 SVG、视频和 GLB；所有页面传服务端实际返回名称。"""
    names = {}
    for kind in ("icon", "image"):
        asset = await request_json(client, "POST", f"/api/workspaces/{workspace_id}/assets/content", json={"asset_type": kind,
            "name": f"drill-{kind}", "original_name": f"drill-{kind}.svg",
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><path fill="currentColor" d="M8 8h48v48H8z"/></svg>'})
        names[kind] = asset["name"]
    for kind, filename, mime, content in (("video", "drill.webm", "video/webm", (root / "runtime/public/video/runtime-video-showcase.webm").read_bytes()),
                                          ("model3d", "drill.glb", "model/gltf-binary", red_model_glb())):
        asset = await request_json(client, "POST", f"/api/workspaces/{workspace_id}/assets/upload",
            data={"asset_type": kind, "name": f"drill-{kind}", "tags": "[]"}, files={"file": (filename, content, mime)})
        names[kind] = asset["name"]

    def source(body: str, imports: str = "") -> str:
        """固定画布、静态类和内容，关闭/开启附图时使用相同源码。"""
        return f'<script setup lang="ts">{imports}</script><template><main class="h-full w-full bg-white p-16 text-slate-900">{body}</main></template>'

    return {
        "text": source('<h1 class="text-5xl">文本固定页面</h1><p class="mt-8 text-2xl">检查文字、换行和留白。</p>'),
        "icon_image": source(f'<h1 class="text-4xl">图标与图片</h1><Icon name="{names["icon"]}" class="size-16" /><AssetImage name="{names["image"]}" class="w-80 h-64" />',
            "import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue';import AssetImage from '@runtime-kit/public/components/assets/AssetImage.v1.vue';"),
        "chart": source('<AssetChart :content="option" class="w-full h-96" />',
            "import AssetChart from '@runtime-kit/public/components/assets/AssetChart.v1.vue';const option=JSON.stringify({xAxis:{type:'category',data:['A','B','C']},yAxis:{type:'value'},series:[{type:'bar',data:[12,20,8]}]});"),
        "video": source(f'<AssetVideo name="{names["video"]}" class="w-full h-96" controls />',
            "import AssetVideo from '@runtime-kit/public/components/assets/AssetVideo.v1.vue';"),
        "model3d": source(f'<AssetModel name="{names["model3d"]}" class="w-full h-96" />',
            "import AssetModel from '@runtime-kit/public/components/assets/AssetModel.v1.vue';"),
        "context": context_source,
    }
