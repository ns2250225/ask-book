"""Build on the target OS/architecture; never cross-compile Python."""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent

def main():
    if not (ROOT / 'frontend/dist/index.html').exists():
        raise SystemExit('Run npm ci && npm run build in frontend first')
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile',
        '--name', 'bookskill-sidecar', '--paths', str(ROOT),
        '--distpath', str(ROOT / 'desktop/dist'), '--workpath', str(ROOT / 'desktop/build'),
        '--specpath', str(ROOT / 'desktop/build'),
        '--add-data', f'{ROOT / "frontend/dist"}:frontend/dist',
        '--collect-all', 'ebooklib', '--collect-all', 'pymupdf',
        '--collect-submodules', 'uvicorn', str(ROOT / 'desktop/sidecar.py')]
    if sys.platform == 'win32':
        command.insert(4, '--windowed')
    subprocess.run(command, cwd=ROOT, check=True)
    suffix = '.exe' if sys.platform == 'win32' else ''
    target = ROOT / 'src-tauri/binaries' / ('bookskill-sidecar' + suffix)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'desktop/dist' / target.name, target)
    print(f'Embedded sidecar ready: {target}')

if __name__ == '__main__':
    main()
