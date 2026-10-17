"""Monta o ZIP do instalador para Windows.

Uso (na raiz do repositório, depois de `npm run build` em web/):

    python windows/package.py [--out dist]

Gera dist/Cordyhome-Windows.zip com o hub, a interface já compilada e os scripts de instalação.
"""

from __future__ import annotations

import argparse
import shutil
import struct
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / "windows"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", ".pytest_cache", ".ruff_cache")


def version() -> str:
    stamp = datetime.now(UTC).strftime("%Y.%m.%d")
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return stamp
    return f"{stamp} ({sha})"


def windows_text(source: Path, target: Path, bom: bool) -> None:
    # PowerShell 5.1 só lê acentos em UTF-8 com BOM; .bat e .ps1 com fim de linha CRLF.
    text = source.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\n", "\r\n")
    target.write_bytes(("﻿" if bom else "").encode("utf-8") + text.encode("utf-8"))


def png_to_ico(png: Path, target: Path) -> None:
    data = png.read_bytes()
    width, height = struct.unpack(">II", data[16:24])
    entry = struct.pack(
        "<BBBBHHII", width % 256, height % 256, 0, 0, 1, 32, len(data), 6 + 16
    )
    target.write_bytes(struct.pack("<HHH", 0, 1, 1) + entry + data)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="dist")
    args = parser.parse_args()

    web_build = ROOT / "web" / "build"
    if not (web_build / "index.html").exists():
        raise SystemExit("web/build não encontrado: rode `npm ci && npm run build` em web/.")

    out = (ROOT / args.out).resolve()
    stage = out / "Cordyhome"
    if stage.exists():
        shutil.rmtree(stage)
    app = stage / "app"
    (app / "hub").mkdir(parents=True)

    shutil.copytree(ROOT / "hub" / "cordyhome", app / "hub" / "cordyhome", ignore=IGNORE)
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copy2(ROOT / "hub" / name, app / "hub" / name)
    shutil.copytree(web_build, app / "web" / "build")
    (app / "VERSION").write_text(version() + "\n", encoding="utf-8")

    windows_text(HERE / "instalar.ps1", stage / "instalar.ps1", bom=True)
    windows_text(HERE / "desinstalar.ps1", stage / "desinstalar.ps1", bom=True)
    windows_text(HERE / "Instalar Cordyhome.bat", stage / "Instalar Cordyhome.bat", bom=False)
    png_to_ico(ROOT / "web" / "static" / "icon-192.png", stage / "cordyhome.ico")

    archive = out / "Cordyhome-Windows.zip"
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(stage.rglob("*")):
            zf.write(path, path.relative_to(out).as_posix())
    shutil.rmtree(stage)
    print(f"{archive} ({archive.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
