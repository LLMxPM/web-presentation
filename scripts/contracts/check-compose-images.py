"""文件功能：校验保留的 Compose 模板所引用的镜像在远程 Registry 的可拉取性（GAT2）。

直接防范模板引用不可拉取镜像导致上线即失败；独立于 test:repository，不引入常规门禁网络依赖。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def find_compose_images(compose_dir: Path) -> dict[str, list[str]]:
    """扫描 compose 目录下的所有 yml 模板，解析服务所使用的镜像列表。"""
    images_by_file: dict[str, list[str]] = {}
    for path in sorted(compose_dir.glob("compose*.yml")):
        images = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            # 匹配形如 image: llmxpm/web-presentation:latest
            match = re.match(r"^image:\s*([^\s#]+)", line)
            if match:
                image = match.group(1).strip("\"'")
                if image not in images:
                    images.append(image)
        if images:
            images_by_file[path.name] = images
    return images_by_file


def inspect_image_manifest(image: str, timeout: int = 30) -> tuple[bool, str]:
    """使用 docker manifest inspect 校验远程镜像清单是否存在。"""
    try:
        res = subprocess.run(
            ["docker", "manifest", "inspect", image],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if res.returncode == 0:
            return True, res.stdout
        error_msg = res.stderr.strip() or res.stdout.strip() or f"退出码 {res.returncode}"
        return False, error_msg
    except Exception as exc:
        return False, str(exc)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compose-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "deploy" / "compose",
        help="Compose 模板目录路径",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="遇到镜像缺失时仅警告不退出 1（用于本地开发或发版前验证）",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="输出校验结果 JSON 报告的路径",
    )
    args = parser.parse_args()

    images_by_file = find_compose_images(args.compose_dir)
    all_images = sorted({img for imgs in images_by_file.values() for img in imgs})

    print(f"[compose-images] 扫描到 {len(images_by_file)} 个模板，共引用 {len(all_images)} 个唯一镜像：")
    for fname, imgs in images_by_file.items():
        print(f"  - {fname}: {', '.join(imgs)}")

    results: dict[str, dict] = {}
    failed_images: list[str] = []

    for image in all_images:
        print(f"[compose-images] 正在检查远程 Manifest: {image} ...", end="", flush=True)
        ok, details = inspect_image_manifest(image)
        if ok:
            print(" [OK]")
            results[image] = {"status": "available", "details": "manifest exists"}
        else:
            print(f" [FAILED] -> {details}")
            results[image] = {"status": "missing_or_error", "error": details}
            failed_images.append(image)

    report = {
        "templates": images_by_file,
        "images": results,
        "failed_count": len(failed_images),
    }

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if failed_images:
        print(f"\n[ERROR] 以下 {len(failed_images)} 个镜像在远程 Registry 无法拉取或不存在：")
        for img in failed_images:
            print(f"  - {img}: {results[img]['error']}")
        if not args.allow_missing:
            sys.exit(1)
        else:
            print("[WARN] --allow-missing 已指定，忽略失败并退出 0。")

    print("\n[SUCCESS] 全部 Compose 模板镜像均可通过 docker manifest inspect 正常拉取。")


if __name__ == "__main__":
    main()
