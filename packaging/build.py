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


def pyinstaller():
    import PyInstaller.__main__

    ipatool = ROOT / "bin" / ("ipatool.exe" if WIN else "ipatool")
    if not ipatool.exists():
        sh(sys.executable, ROOT / "app" / "setup_tools.py")
    sep = os.pathsep
    icon = PKG / ("icon.ico" if WIN else "icon.icns" if MAC else "icon.png")
    args = [
        "--noconfirm", "--clean", "--windowed", "--name", "Vozvrat", "--icon", str(icon),
        "--add-data", f"{ROOT / 'app' / 'ui'}{sep}ui",
        "--add-data", f"{ROOT / 'app' / 'catalog.json'}{sep}.",
        "--add-binary", f"{ipatool}{sep}bin",
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
    sh("hdiutil", "create", "-volname", "Возврат", "-srcfolder", stage, "-ov", "-format", "UDZO", dmg)


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
