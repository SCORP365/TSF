#!/usr/bin/env python3
"""Verified TSF Connect bootstrap entry point.

The bootstrap authenticates with GitHub Device Flow, verifies the signed
manifest and exact source archive, then invokes only installer/install.sh
from the verified private source tree. The GitHub token never leaves this
process and is never passed to the installer.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from bootstrap.installer_flow import retrieve_verified_source
from bootstrap.private_source import SourceDownloadError

BOOTSTRAP_DIR = Path(__file__).resolve().parent
PUBLIC_KEY = BOOTSTRAP_DIR / "keys" / "tsf-release-ed25519-public.pem"
STAGING_ROOT = Path("/var/tmp/tsf-connect-bootstrap")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tsf-connect-bootstrap",
        description="Securely retrieve and launch the signed TSF Connect installer.",
    )
    parser.add_argument(
        "--retrieve-only",
        action="store_true",
        help="verify and extract the signed source without running its installer",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if os.geteuid() != 0:
        print("Запустите bootstrap от root: sudo python3 -m bootstrap.cli", file=sys.stderr)
        return 2
    if not PUBLIC_KEY.is_file() or PUBLIC_KEY.is_symlink():
        print("ERROR: закреплённый публичный ключ подписи отсутствует.", file=sys.stderr)
        return 2

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
        source = retrieve_verified_source(work_dir, PUBLIC_KEY)
        installer = source / "installer" / "install.sh"

        print("2/3. Подпись манифеста и SHA256 архива проверены.")
        print(f"Проверенный исходный код: {source}")

        if args.retrieve_only:
            print("3/3. Режим проверки: установщик не запускался.")
            return 0

        if not installer.is_file() or installer.is_symlink():
            raise SourceDownloadError(
                "Подписанный исходный код пока не содержит installer/install.sh. "
                "Установка безопасно остановлена; ни один файл не запускался."
            )

        print("3/3. Запуск проверенного установщика TSF Connect.")
        result = subprocess.run(
            ["bash", str(installer)],
            cwd=source,
            stdin=None,
            check=False,
            timeout=None,
            env={
                "PATH": os.environ.get("PATH", "/usr/sbin:/usr/bin:/sbin:/bin"),
                "HOME": "/root",
                "LANG": os.environ.get("LANG", "C.UTF-8"),
                "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
                "TSF_BOOTSTRAP_SOURCE": str(source),
            },
        )
        return result.returncode
    except (SourceDownloadError, OSError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
