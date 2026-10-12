"""Сборка «Возврата» для текущей ОС: python packaging/build.py

Windows — build/dist/Vozvrat + dist/VozvratSetup.exe (Inno Setup 6)
macOS   — build/dist/Vozvrat.app + dist/Vozvrat-macOS-<arch>.dmg
Linux   — build/dist/Vozvrat + dist/Vozvrat-Linux-<arch>.tar.gz и .AppImage (если найден appimagetool)

После сборки запускает самопроверку (--smoke). PyInstaller не собирает под другую ОС, поэтому
сборки для macOS и Linux делаются на этих ОС (см. .github/workflows/build.yml).
"""
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packaging"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
WIN, MAC = sys.platform == "win32", sys.platform == "darwin"
ARCH = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"


def sh(*cmd, **kw):
    print("+", " ".join(map(str, cmd)), flush=True)
    subprocess.run(list(map(str, cmd)), check=True, **kw)


SKIP_LICENSES = {"pip", "setuptools", "wheel"}  # инструменты установки, в программу не попадают


def licenses():
    """Папка с лицензиями для сборки: GPL-3.0 проекта, ipatool и всех Python-пакетов окружения сборки.

    pymobiledevice3 распространяется под GPL-3.0, поэтому и сборка с ним идёт под GPL-3.0, а тексты
    лицензий всех вложенных компонентов должны быть внутри неё. Список собирается из метаданных
    установленных пакетов, чтобы не устаревать при смене зависимостей.
    """
    from importlib import metadata

    out = BUILD / "licenses"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    shutil.copy(ROOT / "LICENSE", out / "LICENSE-Vozvrat-GPL-3.0.txt")
    shutil.copy(PKG / "licenses" / "ipatool-MIT.txt", out / "ipatool-MIT.txt")

    parts = ["Сторонние компоненты в сборке «Возврата» и их лицензии.\n"
             "Исходный код «Возврата»: https://github.com/n0hard/back-to-iphone\n"
             "ipatool: https://github.com/majd/ipatool (MIT, текст в ipatool-MIT.txt)\n"]
    minor = f"python{sys.version_info[0]}.{sys.version_info[1]}"
    py_license = next((p for p in (Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "lib" / minor / "LICENSE.txt")
                       if p.exists()), None)
    parts.append(f"\n{'=' * 78}\nPython {platform.python_version()} (PSF License)\n{'=' * 78}\n"
                 + (py_license.read_text(encoding="utf-8", errors="replace") if py_license
                    else "https://docs.python.org/3/license.html\n"))
    dists = {d.metadata["Name"].lower(): d for d in metadata.distributions() if d.metadata["Name"]}
    for name in sorted(dists):
        if name in SKIP_LICENSES:
            continue
        d = dists[name]
        meta = d.metadata
        classifiers = [c.split(" :: ")[-1] for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
        kind = (meta.get("License-Expression") or (meta.get("License") or "").strip().split("\n")[0][:80]
                or ", ".join(classifiers) or "см. текст ниже")
        texts = []
        for f in d.files or []:
            if f.name.upper().startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE", "AUTHORS")):
                try:
                    texts.append(f"--- {f.name} ---\n" + Path(f.locate()).read_bytes().decode("utf-8", "replace").strip())
                except OSError:
                    pass
        url = meta.get("Home-page") or next((u.split(", ", 1)[-1] for u in meta.get_all("Project-URL") or []), "")
        parts.append(f"\n{'=' * 78}\n{meta['Name']} {d.version} ({kind})\n{url}\n{'=' * 78}\n"
                     + ("\n\n".join(texts) if texts else "Текст лицензии в пакете не найден, см. страницу проекта.") + "\n")
    (out / "THIRD-PARTY.txt").write_text("".join(parts), encoding="utf-8")
    return out


def pyinstaller():
    import PyInstaller.__main__

    ipatool = ROOT / "bin" / ("ipatool.exe" if WIN else "ipatool")
    sh(sys.executable, ROOT / "app" / "setup_tools.py")  # ставит закреплённую версию, если сейчас стоит другая
    sep = os.pathsep
    icon = PKG / ("icon.ico" if WIN else "icon.icns" if MAC else "icon.png")
    args = [
        "--noconfirm", "--clean", "--windowed", "--name", "Vozvrat", "--icon", str(icon),
        "--add-data", f"{ROOT / 'app' / 'ui'}{sep}ui",
        "--add-data", f"{ROOT / 'app' / 'catalog.json'}{sep}.",
        "--add-binary", f"{ipatool}{sep}bin",
        "--add-data", f"{licenses()}{sep}licenses",
        "--collect-all", "pymobiledevice3",
        "--collect-submodules", "rich",  # rich грузит таблицы Unicode динамически — без этого падают справка и ошибки pmd3
        "--paths", str(ROOT / "app"),
        "--distpath", str(BUILD / "dist"), "--workpath", str(BUILD / "work"), "--specpath", str(BUILD),
    ]
    if not sys.platform.startswith("linux"):
        args += ["--collect-submodules", "webview"]
    if MAC:
        args += ["--osx-bundle-identifier", "io.github.n0hard.vozvrat"]
    PyInstaller.__main__.run([*args, str(ROOT / "app" / "main.py")])


def executable():
    if MAC:
        return BUILD / "dist" / "Vozvrat.app" / "Contents" / "MacOS" / "Vozvrat"
    return BUILD / "dist" / "Vozvrat" / ("Vozvrat.exe" if WIN else "Vozvrat")


def smoke():
    p = subprocess.run([str(executable()), "--smoke"], capture_output=True, text=True, timeout=300)
    print(p.stdout, p.stderr)
    if p.returncode != 0:
        sys.exit(f"Самопроверка не прошла (код {p.returncode})")


def package_windows():
    iscc = next((Path(p) for p in (
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
    ) if p.exists()), None)
    if not iscc:
        print("Inno Setup 6 не найден — инсталлятор не собран, программа лежит в build/dist/Vozvrat")
        return
    for attempt in range(3):  # антивирус иногда держит свежий exe — «EndUpdateResource failed»
        if subprocess.run([str(iscc), str(PKG / "installer.iss")]).returncode == 0:
            return
    sys.exit("Inno Setup не смог собрать инсталлятор")


def package_macos():
    app = BUILD / "dist" / "Vozvrat.app"
    # ad-hoc подпись всего бандла: без неё Apple Silicon не запустит вложенные бинарники (ipatool)
    sh("codesign", "--force", "--deep", "--sign", "-", app)
    stage = BUILD / "dmg"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    shutil.copytree(app, stage / "Vozvrat.app", symlinks=True)
    os.symlink("/Applications", stage / "Applications")
    dmg = DIST / f"Vozvrat-macOS-{ARCH}.dmg"
    dmg.unlink(missing_ok=True)
    cmd = ["hdiutil", "create", "-volname", "Возврат", "-srcfolder", stage, "-ov", "-format", "UDZO", dmg]
    for attempt in range(5):  # на машинах GitHub hdiutil иногда отвечает «Resource busy» — помогает повтор
        try:
            return sh(*cmd)
        except subprocess.CalledProcessError:
            if attempt == 4:
                raise
            time.sleep(10)


def package_linux():
    src = BUILD / "dist" / "Vozvrat"
    tgz = DIST / f"Vozvrat-Linux-{ARCH}.tar.gz"
    with tarfile.open(tgz, "w:gz") as tar:
        tar.add(src, arcname="Vozvrat")
    print("Готово:", tgz)

    tool = os.environ.get("APPIMAGETOOL") or shutil.which("appimagetool")
    if not tool:
        print("appimagetool не найден — AppImage не собран")
        return
    appdir = BUILD / "Vozvrat.AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    shutil.copytree(src, appdir / "usr" / "lib" / "vozvrat", symlinks=True)
    shutil.copy(PKG / "linux" / "vozvrat.desktop", appdir / "vozvrat.desktop")
    shutil.copy(PKG / "icon.png", appdir / "vozvrat.png")
    shutil.copy(PKG / "linux" / "AppRun", appdir / "AppRun")
    (appdir / "AppRun").chmod(0o755)
    image = DIST / f"Vozvrat-Linux-{ARCH}.AppImage"
    arch = {"x64": "x86_64", "arm64": "aarch64"}[ARCH]
    # в CI нет FUSE — appimagetool (сам AppImage) запускаем через распаковку
    extract = ["--appimage-extract-and-run"] if os.environ.get("CI") else []
    sh(tool, *extract, "--no-appstream", appdir, image, env={**os.environ, "ARCH": arch})


def main():
    DIST.mkdir(exist_ok=True)
    pyinstaller()
    smoke()
    (package_windows if WIN else package_macos if MAC else package_linux)()
    print("Сборка завершена:", *sorted(p.name for p in DIST.iterdir()))


if __name__ == "__main__":
    main()
