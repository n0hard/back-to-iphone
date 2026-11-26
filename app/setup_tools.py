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
VERSION = "2.8.1"
URL = "https://github.com/majd/ipatool/releases/download/v{v}/ipatool-{v}-{system}-{arch}.tar.gz"
SHA256 = {
    ("windows", "amd64"): "a8ccd8075bc083f99caa49976997860ba5e0e3e8f76b450360cd805262542e97",
    ("windows", "arm64"): "60cce6a66d7ad5f3bf2e301a8fc8b8dc74a406d5bcc15496398a8f997854fcad",
    ("macos", "amd64"): "8d1d93c1f72724cec01e72dab30ecb8eb3faf4c783f71d2310c2db3c7976efbb",
    ("macos", "arm64"): "3ad673375ea6bc479df0340df03950c3f6669ab554466b05e4bb99b3369d0dd2",
    ("linux", "amd64"): "c5a7d35d98a0ac41fbb9d21c19437c3e6006c6e32556f484d09ed26872f9c283",
    ("linux", "arm64"): "64dc6311acbd92f8165fe382ee86852f520b23355dae65933cb0f60177357116",
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
