"""Скачивает ipatool (github.com/majd/ipatool) в ../bin и проверяет SHA-256.

Версия и контрольные суммы закреплены здесь, а не берутся из «последнего» релиза: программа разбирает
JSON-вывод ipatool, и новая версия с другим форматом сломала бы сборку без изменений в нашем коде.
Сумма из репозитория защищает и от подмены файла в релизе, а не только от повреждения при скачивании.

Чтобы обновить ipatool: поменяйте VERSION и SHA256 (суммы — из файлов *.sha256sum релиза,
сверьте их с sha256 скачанных архивов), соберите программу и проверьте вход и установку.
"""
import hashlib
import io
import platform
import sys
import tarfile
from pathlib import Path

import requests

BIN = Path(__file__).resolve().parent.parent / "bin"
VERSION = "2.7.0"
URL = "https://github.com/majd/ipatool/releases/download/v{v}/ipatool-{v}-{system}-{arch}.tar.gz"
SHA256 = {
    ("windows", "amd64"): "b729608716908be287c2e6972f9e8cd05f879810ae5d182fc856c9e57cca0dd5",
    ("windows", "arm64"): "85ab35a268b47e1729412178063fe11621cae1135f33d3b9ab5233d436bf2562",
    ("macos", "amd64"): "05f48994d8b3cfefe7ea1172a0ac0b28715888e9df0af38cf3e490d2ed592263",
    ("macos", "arm64"): "5ae100d4520cf4b3f4374239e5925a9ad9a8dc02abc16bae27479e7ae99aca33",
    ("linux", "amd64"): "68372de9743d468296f2dba5b413a3e7df56ad0c85b8d0f4f0f6c9b8b53a54e8",
    ("linux", "arm64"): "133c3fb754bafcd61698ba6047b48096c7033345529f57d7a83d281f8a403c23",
}


def target():
    system = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "amd64"
    return system, arch


def main():
    system, arch = target()
    exe = BIN / ("ipatool.exe" if system == "windows" else "ipatool")
    marker = BIN / "ipatool.version"  # иначе после смены VERSION у разработчика остался бы старый ipatool
    if exe.exists() and marker.exists() and marker.read_text().strip() == VERSION and "--force" not in sys.argv:
        print(f"ipatool {VERSION} уже установлен: {exe}")
        return
    expected = SHA256.get((system, arch))
    if not expected:
        sys.exit(f"Нет сборки ipatool {VERSION} для {system}-{arch}")
    url = URL.format(v=VERSION, system=system, arch=arch)
    print(f"Скачиваю ipatool {VERSION} ({system}-{arch})…")
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    data = r.content
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        sys.exit(f"Контрольная сумма ipatool не совпала: {actual} != {expected}")
    BIN.mkdir(exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        member = next(m for m in tar.getmembers() if m.isfile() and Path(m.name).name.startswith("ipatool"))
        exe.write_bytes(tar.extractfile(member).read())
    exe.chmod(0o755)
    marker.write_text(VERSION)
    print(f"Готово: {exe}")


if __name__ == "__main__":
    main()
