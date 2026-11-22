#!/usr/bin/env python3
"""TSF Connect bootstrap: GitHub Device Flow and pinned private source."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from bootstrap.installer_flow import SOURCE_COMMIT, retrieve_source
from bootstrap.private_source import SourceDownloadError

STAGING_ROOT = Path("/var/tmp/tsf-connect-bootstrap")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tsf-connect-bootstrap",
        description="Retrieve and launch the pinned TSF Connect installer from private GitHub.",
    )
    parser.add_argument("--retrieve-only", action="store_true",
                        help="download and extract the pinned source without running its installer")
    parser.add_argument("--resume", action="store_true",
                        help="continue a previously interrupted TSF Connect installation")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.retrieve_only and args.resume:
        print("ERROR: --retrieve-only and --resume cannot be used together.", file=sys.stderr)
        return 2
    if os.geteuid() != 0:
        print("Запустите bootstrap от root: sudo python3 -m bootstrap.cli", file=sys.stderr)
        return 2

    work_dir = None
    try:
        STAGING_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        if STAGING_ROOT.is_symlink() or not STAGING_ROOT.is_dir():
            raise SourceDownloadError("Небезопасный каталог временных файлов bootstrap.")
        st = STAGING_ROOT.stat(follow_symlinks=False)
        if st.st_uid != os.geteuid() or (st.st_mode & 0o077):
            raise SourceDownloadError("Каталог bootstrap должен принадлежать root и иметь права 0700.")
        work_dir = Path(tempfile.mkdtemp(prefix="release-", dir=STAGING_ROOT))
        os.chmod(work_dir, 0o700)

        print("1/3. Авторизация GitHub через QR-код Device Flow.")
        source, digest = retrieve_source(work_dir)
        installer = source / "installer" / "install.sh"

        print("2/3. Получен исходный код из приватного репозитория.")
        print(f"Commit: {SOURCE_COMMIT}")
        print(f"SHA-256 архива: {digest}")
        print(f"Исходный код: {source}")

        if args.retrieve_only:
            print("3/3. Режим проверки: установщик не запускался.")
            return 0
        if not installer.is_file() or installer.is_symlink():
            raise SourceDownloadError(
                "В закреплённом коммите отсутствует installer/install.sh. "
                "Установка остановлена; ни один файл не запускался."
            )

        print("3/3. Запуск единого установщика TSF Connect.")
        command = ["bash", str(installer)]
        if args.resume:
            command.append("--resume")
        result = subprocess.run(
            command, cwd=source, stdin=None, check=False, timeout=None,
            env={
                "PATH": os.environ.get("PATH", "/usr/sbin:/usr/bin:/sbin:/bin"),
                "HOME": "/root",
                "LANG": os.environ.get("LANG", "C.UTF-8"),
                "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
                "TSF_BOOTSTRAP_SOURCE": str(source),
            },
        )
        if result.returncode == 0:
            shutil.rmtree(work_dir, ignore_errors=True)
            work_dir = None
            print("Временные исходники удалены; установленная копия находится в /opt/tsf-connect.")
        return result.returncode
    except (SourceDownloadError, OSError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if work_dir is not None and not args.retrieve_only:
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
