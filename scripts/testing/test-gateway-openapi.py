"""文件功能：使用隔离 Docker 网络和真实 Nginx 验证网关代理成功、失败及 SPA 行为。"""

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from uuid import uuid4


def docker(*args: str) -> str:
    """执行 Docker 命令，失败保留原始诊断，不吞掉非零退出。"""
    return subprocess.check_output(['docker', *args], text=True).strip()


def main() -> None:
    """创建受控上游和真实网关，用 HTTP 验收后清理本次容器与网络。"""
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('gateway_check', Path(__file__).with_name('check-gateway-openapi.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    name = 'wp-contract-' + uuid4().hex[:10]
    network = name + '-net'
    containers = []
    docker('network', 'create', network)
    try:
        with tempfile.TemporaryDirectory(prefix='wp-gateway-') as temporary:
            directory = Path(temporary)
            document = {'openapi': '3.1.0', 'paths': {path: {method: {}} for path, method in [
                ('/api/v1/themes', 'post'), ('/api/v1/styles', 'post'), ('/api/v1/projects/{project_id}/route-tree', 'put')]}}
            (directory / 'openapi.json').write_text(json.dumps(document), encoding='utf-8')
            (directory / 'index.html').write_text('<html>editor-fixture</html>', encoding='utf-8')
            (directory / 'upstream.conf').write_text('server { listen 8000; root /fixture; location = /api/v1/system/health { default_type application/json; return 200 \'{"status":"ok"}\'; } location = /openapi.json { default_type application/json; try_files $uri =503; } }', encoding='utf-8')
            backend = name + '-backend'
            docker('run', '-d', '--name', backend, '--network', network, '--network-alias', 'backend', '--network-alias', 'runtime', '-v', f'{directory.as_posix()}:/fixture:ro', '-v', f'{(directory / "upstream.conf").as_posix()}:/etc/nginx/conf.d/default.conf:ro', 'nginx:1.28-alpine')
            containers.append(backend)
            gateway = name + '-gateway'
            docker('run', '-d', '--name', gateway, '--network', network, '-p', '127.0.0.1::80', '-v', f'{(root / "docker/nginx/web-presentation.conf").as_posix()}:/etc/nginx/conf.d/default.conf:ro', '-v', f'{directory.as_posix()}:/usr/share/nginx/html:ro', 'nginx:1.28-alpine')
            containers.append(gateway)
            endpoint = 'http://' + docker('port', gateway, '80/tcp')
            for attempt in range(30):
                try:
                    with urlopen(endpoint + '/healthz', timeout=1) as response:
                        assert response.status == 200
                    break
                except (URLError, TimeoutError):
                    if attempt == 29:
                        raise
                    time.sleep(0.2)
            module.check(endpoint)
            with urlopen(endpoint + '/api/v1/system/health') as response:
                assert json.load(response)['status'] == 'ok'
            with urlopen(endpoint + '/editor/deep-link') as response:
                assert b'editor-fixture' in response.read()
            (directory / 'openapi.json').unlink()
            try:
                urlopen(endpoint + '/openapi.json')
                raise AssertionError('上游 503 被隐藏')
            except HTTPError as error:
                assert error.code == 503
                assert b'editor-fixture' not in error.read()
            print('真实 Nginx：上游 503 透传、原 API 与 Editor SPA 检查通过。')
    finally:
        for container in reversed(containers):
            docker('rm', '-f', container)
        docker('network', 'rm', network)


if __name__ == '__main__':
    main()
