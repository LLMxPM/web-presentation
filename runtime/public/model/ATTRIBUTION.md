<!-- 文件功能：登记 Runtime 本地三维示例模型的来源、作者与授权，供再分发时保留署名。 -->
# 本地三维示例模型

`runtime/public/model/` 下的 GLB 仅用于本地 fixture 演示 AssetModel / ModelViewer 的渲染链路，不参与平台构建产物。所有文件均从公开仓库直接下载、未作修改。

| 文件 | 模型 | 来源 | 作者 | 授权 |
| --- | --- | --- | --- | --- |
| `box.glb` | Box | [KhronosGroup/glTF-Sample-Assets](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/Box) | Cesium | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| `box-animated.glb` | Box Animated | [KhronosGroup/glTF-Sample-Assets](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/BoxAnimated) | Cesium | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| `rigged-figure.glb` | Rigged Figure | [KhronosGroup/glTF-Sample-Assets](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/RiggedFigure) | Cesium | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| `fox.glb` | Fox | [KhronosGroup/glTF-Sample-Assets](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/Fox) | PixelMannen（模型，CC0）、tomkranis（绑定与动画，CC BY 4.0）、@AsoboStudio 与 @scurest（glTF 转换，CC BY 4.0） | CC0 1.0 + [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| `robot-expressive.glb` | Robot Expressive | [mrdoob/three.js](https://github.com/mrdoob/three.js/tree/dev/examples/models/gltf/RobotExpressive) | Tomás Laulhé（模型）、Don McCurdy（表情形变与转换） | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) |

## 维护约定

- 新增示例模型时同步更新本表，保留作者、来源链接与授权；CC BY 资源必须保留署名。
- 不要放入仅限非商业使用（NC）或来源不明的模型。
- 单个文件建议控制在 5 MiB 以内；超过仓库 `.gitattributes` 的二进制阈值时先确认是否需要入库。
