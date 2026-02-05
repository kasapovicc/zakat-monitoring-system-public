#!/usr/bin/env python3
"""
Build script for Zekat macOS app

Runs PyInstaller and produces dist/Zekat.app
"""

import sys
import subprocess
import shutil
from pathlib import Path


def main():
    """Build the macOS app bundle"""
    print("=" * 60)
    print("Building Zekat.app")
    print("=" * 60)

    # Check if PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("\n❌ PyInstaller not found!")
        print("Install it with: pip install pyinstaller")
        return 1

    # Clean previous builds
    print("\n1. Cleaning previous builds...")
    build_dir = Path("build")
    dist_dir = Path("dist")

    if build_dir.exists():
        shutil.rmtree(build_dir)
        print("   ✓ Removed build/")

    if dist_dir.exists():
        shutil.rmtree(dist_dir)
        print("   ✓ Removed dist/")

    # Run PyInstaller
    print("\n2. Running PyInstaller...")
    result = subprocess.run(
        ["pyinstaller", "zekat.spec", "--clean"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("❌ PyInstaller failed!")
        print(result.stderr)
        return 1

    print("   ✓ PyInstaller completed")

    # Ad-hoc code sign the app bundle
    print("\n3. Code signing (ad-hoc)...")
    sign_result = subprocess.run(
        ["codesign", "--force", "--deep", "-s", "-", "dist/Zekat.app"],
        capture_output=True,
        text=True
    )
    if sign_result.returncode == 0:
        print("   ✓ Ad-hoc code signing completed")
    else:
        print("   ⚠ Ad-hoc signing failed (app will still work, may trigger Gatekeeper)")
        if sign_result.stderr:
            print(f"     {sign_result.stderr.strip()}")

    # Copy install helper into dist/
    install_script = Path("install-zekat.command")
    if install_script.exists():
        shutil.copy2(install_script, dist_dir / "install-zekat.command")
        print("   ✓ Copied install-zekat.command to dist/")

    # Check if app was created
    app_path = dist_dir / "Zekat.app"
    if not app_path.exists():
        print("\n❌ Zekat.app not found in dist/")
        return 1

    # Verify critical modules are bundled
    print("\n4. Verifying bundled dependencies...")
    internal_dir = dist_dir / "Zekat" / "_internal"
    critical_modules = {
        'uvicorn': [internal_dir / "uvicorn"],
        'starlette': [internal_dir / "starlette"],
        'fastapi': [internal_dir / "fastapi"],
        'h11': [internal_dir / "h11", internal_dir / "h11.pyc"],
        'anyio': [internal_dir / "anyio"],
        'sniffio': [internal_dir / "sniffio", internal_dir / "sniffio.pyc"],
        'run_app.py': [internal_dir / "run_app.py"],
        'rumps': [internal_dir / "rumps"],
        'webview': [internal_dir / "webview"],
        'app/window.py': [internal_dir / "app" / "window.py"],
    }

    missing_modules = []
    for name, paths in critical_modules.items():
        found = any(path.exists() for path in paths)
        if found:
            print(f"   ✓ {name}")
        else:
            print(f"   ❌ {name} - MISSING!")
            missing_modules.append(name)

    if missing_modules:
        print(f"\n❌ Build incomplete! Missing critical modules: {', '.join(missing_modules)}")
        print("   The app will not work without these dependencies.")
        return 1

    print(f"\n✅ Build successful!")
    print(f"   App location: {app_path.absolute()}")
    print(f"   Size: {get_dir_size(app_path):.1f} MB")

    # Instructions
    print("\n" + "=" * 60)
    print("Next Steps:")
    print("=" * 60)
    print("\n1. Test the app:")
    print("   open dist/Zekat.app")
    print("\n2. If macOS blocks the app:")
    print("   Go to System Settings > Privacy & Security > click 'Open Anyway'")
    print("   Or run: xattr -cr dist/Zekat.app")
    print("\n3. To create a distributable archive:")
    print("   cd dist && zip -r Zekat.zip Zekat.app install-zekat.command")
    print("\n4. Or create a DMG (requires create-dmg):")
    print("   create-dmg dist/Zekat.app dist/")

    return 0


def get_dir_size(path: Path) -> float:
    """Get directory size in MB"""
    total = 0
    try:
        for item in path.rglob('*'):
            if item.is_file():
                total += item.stat().st_size
    except Exception:
        pass
    return total / (1024 * 1024)


if __name__ == "__main__":
    sys.exit(main())
