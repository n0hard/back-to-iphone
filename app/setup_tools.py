"""Скачивает ipatool (github.com/majd/ipatool) в ../bin и проверяет SHA-256 из официального релиза."""
import hashlib
import io
import platform
import sys
import tarfile
from pathlib import Path

import requests

BIN = Path(__file__).resolve().parent.parent / "bin"
REPO = "majd/ipatool"


def target():
    system = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "amd64"
    return system, arch


def main():
    system, arch = target()
    exe = BIN / ("ipatool.exe" if system == "windows" else "ipatool")
    if exe.exists() and "--force" not in sys.argv:
        print(f"ipatool уже установлен: {exe}")
        return
    rel = requests.get(f"https://api.github.com/repos/{REPO}/releases/latest", timeout=30).json()
    suffix = f"-{system}-{arch}.tar.gz"
    assets = {a["name"]: a["browser_download_url"] for a in rel["assets"]}
    name = next(n for n in assets if n.endswith(suffix))
    print(f"Скачиваю {name} ({rel['tag_name']})…")
    data = requests.get(assets[name], timeout=300).content
    expected = requests.get(assets[name + ".sha256sum"], timeout=30).text.split()[0].lower()
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        sys.exit(f"Контрольная сумма не совпала: {actual} != {expected}")
    BIN.mkdir(exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        member = next(m for m in tar.getmembers() if m.isfile() and Path(m.name).name.startswith("ipatool"))
        exe.write_bytes(tar.extractfile(member).read())
    exe.chmod(0o755)
    print(f"Готово: {exe}")


if __name__ == "__main__":
    main()
