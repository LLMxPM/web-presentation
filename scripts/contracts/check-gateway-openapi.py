"""文件功能：只读验证外部 Gateway 的 OpenAPI 内容和关键 CLI 请求操作。"""

import argparse
import json
from urllib.request import urlopen


def check(endpoint: str) -> None:
    """从网关根地址读取真实 HTTP 响应；任何内容或契约异常直接失败。"""
    with urlopen(endpoint.rstrip('/') + '/openapi.json', timeout=10) as response:
        assert response.status == 200, f'HTTP {response.status}'
        assert response.headers.get_content_type() == 'application/json', 'OpenAPI Content-Type 不是 application/json'
        document = json.load(response)
    assert isinstance(document, dict) and str(document.get('openapi', '')).startswith('3.'), 'OpenAPI 根结构无效'
    assert isinstance(document.get('paths'), dict), '缺少 paths 对象'
    for path, method in [('/api/v1/themes', 'post'), ('/api/v1/styles', 'post'), ('/api/v1/projects/{project_id}/route-tree', 'put')]:
        assert isinstance(document['paths'].get(path, {}).get(method), dict), f'缺少 {method.upper()} {path}'
    print('Gateway OpenAPI 内容及主题、样式、路由操作检查通过。')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('endpoint', help='必须使用外部 Gateway 根地址，不是 Backend 内网地址')
    check(parser.parse_args().endpoint)
