"""文件功能：使用无敏感信息的 scratch 构建，验证根级 Docker 排除规则覆盖所有模块。"""
from pathlib import Path
import subprocess
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    """只发送临时夹具到 Docker，验证环境文件、密钥和缓存被排除，示例配置仍可交付。"""

    with tempfile.TemporaryDirectory(prefix="wp-docker-context-") as directory:
        root = Path(directory)
        context = root / "context"
        context.mkdir()
        (context / ".dockerignore").write_bytes((REPO_ROOT / ".dockerignore").read_bytes())
        blocked = [".env", "backend/.env", "editor/.env.local", "runtime/.env", "renderer/.env", "deploy/.env", "deploy/secrets/render_service_credential", ".tmp/cache"]
        allowed = [".env.example", "backend/.env.example", "runtime/.env.production.example"]
        for name in blocked + allowed:
            target = context / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("SYNTHETIC=fixture-only\n", encoding="utf-8")
        (context / "Dockerfile").write_text("FROM scratch\nCOPY . /context\n", encoding="utf-8")
        output = root / "output"
        subprocess.run(["docker", "build", "--output", f"type=local,dest={output}", str(context)], check=True)
        leaked = [name for name in blocked if (output / "context" / name).exists()]
        missing = [name for name in allowed if not (output / "context" / name).exists()]
        if leaked or missing:
            raise RuntimeError(f"Docker 排除边界错误：未排除={leaked}，误排除={missing}")
        print("[docker] 全模块环境文件、密钥与临时目录排除规则验证通过")


if __name__ == "__main__":
    main()
