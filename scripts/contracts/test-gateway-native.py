"""文件功能：用专属本机 Nginx 验证生产 Gateway 的 OpenAPI/OAuth/SPA 路由，不依赖 Docker。"""

import argparse
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    """保留授权跳转的原始响应，测试不能访问外部回调。"""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        """不跟随 Location，只验证真实 Nginx 的透传。"""
        return None


def free_port():
    """选择专属 loopback 端口，不复用开发服务。"""
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def validate(endpoint, opener, document, state):
    """用真实 HTTP 验证完整契约、发现、跳转、Basic/错误、请求大小和 SPA 边界。"""
    with opener.open(endpoint + '/openapi.json', timeout=10) as response:
        assert response.headers.get_content_type() == 'application/json'
        assert json.load(response) == document
    for path in ('/editor/deep-link', '/oauth/consent'):
        with opener.open(endpoint + path, timeout=5) as response:
            assert b'editor-fixture' in response.read()
    with opener.open(endpoint + '/.well-known/oauth-authorization-server', timeout=5) as response:
        assert json.load(response)['issuer'] == 'https://oauth-fixture.test'
    cases = [('/oauth/authorize', None, 302), ('/oauth/token', b'grant_type=invalid', 400),
             ('/oauth/introspect', b'token=synthetic-inactive', 400), ('/oauth/revoke', b'token=synthetic-inactive', 400),
             ('/oauth/introspect', b'x' * 20000, 413)]
    for path, body, status in cases:
        request = Request(endpoint + path, data=body, headers={'Authorization': 'Basic synthetic-service',
            'Content-Type': 'application/x-www-form-urlencoded', 'X-Request-ID': 'native-gateway-test'})
        try:
            opener.open(request, timeout=5)
            raise AssertionError('上游错误或重定向被隐藏')
        except HTTPError as error:
            assert error.code == status
            if status == 302:
                assert error.headers['Location'] == 'https://oauth-fixture.test/oauth/consent'
            elif status == 400:
                assert json.load(error)['error'] == 'invalid_request'
                assert error.headers['X-Request-ID'] == 'native-gateway-test'
                assert error.headers['WWW-Authenticate'] == 'Basic realm="fixture"'
    state['available'] = False
    try:
        opener.open(endpoint + '/openapi.json', timeout=5)
        raise AssertionError('OpenAPI 上游 503 被 SPA 隐藏')
    except HTTPError as error:
        assert error.code == 503 and b'editor-fixture' not in error.read()


def main(binary, openapi_file):
    """读取生产模板，只替换专属端口/文件位置；受控上游不计 OAuth 业务或容器验收。"""
    root = Path(__file__).resolve().parents[2]
    binary = binary.resolve(strict=True)
    document = json.loads(openapi_file.read_text(encoding='utf-8-sig'))
    assert str(document['openapi']).startswith('3.') and document['paths']
    state = {'available': True}

    class Upstream(BaseHTTPRequestHandler):
        """仅提供可观察的 HTTP 上游响应，生产业务另由消费者联测验证。"""

        def do_GET(self):
            """按请求路径返回发现/契约/跳转，保留代理 Header 的断言。"""
            status, body = 200, {}
            if self.path == '/openapi.json':
                status, body = (200, document) if state['available'] else (503, {'error': 'unavailable'})
            elif self.path == '/.well-known/oauth-authorization-server':
                body = {'issuer': 'https://oauth-fixture.test'}
            elif self.path == '/oauth/authorize':
                status = 302
            else:
                assert self.path in {'/oauth/token', '/oauth/introspect', '/oauth/revoke'}
                assert self.headers['Authorization'] == 'Basic synthetic-service'
                assert self.headers['X-Request-ID'] == 'native-gateway-test'
                status, body = 400, {'error': 'invalid_request'}
            encoded = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.send_header('X-Request-ID', self.headers.get('X-Request-ID', 'fixture'))
            self.send_header('WWW-Authenticate', 'Basic realm="fixture"')
            if status == 302:
                self.send_header('Location', 'https://oauth-fixture.test/oauth/consent')
            self.end_headers()
            self.wfile.write(encoded)

        def do_POST(self):
            """消费测试 form 后共用协议响应，不保存或打印请求体。"""
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            self.do_GET()

        def log_message(self, format, *args):
            """测试上游不打印请求或 Header。"""
            return

    temporary_root = root / '.tmp/gateway-native'
    temporary_root.mkdir(parents=True, exist_ok=True)
    upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix='run-', dir=temporary_root) as temporary:
            directory = Path(temporary).resolve()
            assert directory.is_relative_to(temporary_root.resolve())
            (directory / 'logs').mkdir()
            (directory / 'temp').mkdir()
            (directory / 'index.html').write_text('<html>editor-fixture</html>', encoding='utf-8')
            port, backend = free_port(), f'127.0.0.1:{upstream.server_port}'
            template = (root / 'deploy/docker/nginx/web-presentation.conf').read_text(encoding='utf-8')
            template = template.replace('listen 80;', f'listen 127.0.0.1:{port};').replace('backend:8000', backend).replace('runtime:7373', backend)
            template = template.replace('/usr/share/nginx/html', directory.as_posix()).replace('/dev/stderr', (directory / 'logs/error.log').as_posix())
            (directory / 'gateway.conf').write_text(template, encoding='utf-8')
            (directory / 'nginx.conf').write_text('worker_processes 1; worker_shutdown_timeout 5s; pid logs/nginx.pid; '
                'error_log logs/error.log warn; events {worker_connections 128;} http {include gateway.conf;}', encoding='utf-8')
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            command = [str(binary), '-p', directory.as_posix() + '/', '-c', 'nginx.conf']
            subprocess.run([*command, '-t'], check=True, capture_output=True, creationflags=flags)
            process = subprocess.Popen(command, creationflags=flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            opener = build_opener(ProxyHandler({}), NoRedirect())
            endpoint = f'http://127.0.0.1:{port}'
            try:
                for attempt in range(50):
                    assert process.poll() is None, '本轮 Nginx 提前退出'
                    try:
                        with opener.open(endpoint + '/healthz', timeout=1) as response:
                            assert response.status == 200
                        break
                    except (URLError, TimeoutError):
                        if attempt == 49:
                            raise
                        time.sleep(.1)
                validate(endpoint, opener, document, state)
            finally:
                subprocess.run([*command, '-s', 'quit'], check=True, capture_output=True, creationflags=flags)
                process.wait(timeout=10)
    finally:
        upstream.shutdown()
        thread.join(timeout=5)
        upstream.server_close()
    print('本机真实 Nginx：生产 Gateway 的完整 OpenAPI、OAuth/Basic/错误与 SPA 边界通过。')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nginx-binary', type=Path, required=True)
    parser.add_argument('--openapi-file', type=Path, required=True)
    args = parser.parse_args()
    main(args.nginx_binary, args.openapi_file)
