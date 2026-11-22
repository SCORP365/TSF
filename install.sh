#!/usr/bin/env bash
# TSF Connect public bootstrap: authenticate to GitHub and fetch the private installer.
set -Eeuo pipefail

fail() { printf 'ОШИБКА: %s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || fail "Запустите от root: sudo bash install.sh"
[[ $# -le 1 && ( $# -eq 0 || "$1" == "--resume" ) ]] || fail "Использование: install.sh [--resume]"
[[ -r /etc/os-release ]] || fail "Не удалось определить ОС."
. /etc/os-release
[[ "${ID:-}" == ubuntu && "${VERSION_ID:-}" == 24.04 ]] || fail "Поддерживается Ubuntu 24.04 LTS."
[[ "$(dpkg --print-architecture)" == amd64 ]] || fail "Поддерживается архитектура amd64."
command -v systemctl >/dev/null 2>&1 || fail "Требуется systemd."

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates python3 qrencode

WORK="$(mktemp -d /var/tmp/tsf-connect-bootstrap.XXXXXX)"
chmod 0700 "$WORK"
cleanup() { rm -rf -- "$WORK"; }
trap cleanup EXIT

echo
echo "======================================================"
echo "          TSF CONNECT — ЕДИНЫЙ УСТАНОВЩИК"
echo "======================================================"
echo "Получение проверенных исходников из приватного GitHub."
echo "Сейчас появится QR-код и одноразовый код авторизации."
echo

python3 - "$WORK/source" <<'PY'
import base64
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

OWNER = "SCORP365"
REPO = "TSF-Connect"
REF = "test/no-ed25519"
CLIENT_ID = "Iv23liiXhUA7P0zNBVmn"
API = "https://api.github.com"
DEVICE_URL = "https://github.com/login/device"
DEVICE_CODE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"
DEST = pathlib.Path(sys.argv[1]).resolve()
MAX_TOTAL = 120 * 1024 * 1024
MAX_FILE = 25 * 1024 * 1024

def request(url, method="GET", data=None, token=None, accept="application/vnd.github+json"):
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "TSF-Connect-Bootstrap"}
    if token:
        headers["Authorization"] = "Bearer " + token
    payload = None
    if data is not None:
        payload = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read(MAX_TOTAL + 1024 * 1024)
    except urllib.error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", "replace")
        raise RuntimeError(f"GitHub API HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Не удалось подключиться к GitHub.") from exc
    try:
        return json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("GitHub вернул некорректный ответ.") from exc

def authorize():
    device = request(DEVICE_CODE_URL, "POST", {"client_id": CLIENT_ID},
                     accept="application/json")
    if device.get("error"):
        raise RuntimeError("Не удалось начать GitHub Device Flow: " + str(device.get("error_description") or device["error"]))
    code, user_code = device.get("device_code"), device.get("user_code")
    verify = device.get("verification_uri")
    if not all(isinstance(x, str) and x for x in (code, user_code)) or verify != DEVICE_URL:
        raise RuntimeError("GitHub вернул некорректные параметры Device Flow.")
    interval = max(5, int(device.get("interval", 5)))
    deadline = time.monotonic() + int(device.get("expires_in", 900))
    subprocess.run(["qrencode", "-t", "ANSIUTF8", "-m", "2", verify],
                   check=True, stdin=subprocess.DEVNULL)
    print("\nОткройте " + verify)
    print("Одноразовый код: " + user_code)
    print("Подтвердите доступ приложения TSF Connect к приватному SCORP365/TSF-Connect.")
    while time.monotonic() < deadline:
        time.sleep(interval)
        result = request(TOKEN_URL, "POST", {
            "client_id": CLIENT_ID, "device_code": code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
        }, accept="application/json")
        error = result.get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        if error:
            raise RuntimeError("GitHub OAuth: " + str(result.get("error_description") or error))
        access = result.get("access_token")
        if isinstance(access, str) and access and result.get("token_type", "").lower() == "bearer":
            return access
        raise RuntimeError("GitHub не выдал токен доступа.")
    raise RuntimeError("Срок действия кода истёк. Запустите установщик повторно.")

def api(token, path):
    return request(f"{API}/repos/{OWNER}/{REPO}/{path}", token=token)

def main():
    token = authorize()
    ref = api(token, "git/ref/heads/" + urllib.parse.quote(REF, safe="/"))
    commit_sha = ref.get("object", {}).get("sha")
    if not isinstance(commit_sha, str) or len(commit_sha) != 40:
        raise RuntimeError("Не удалось определить commit приватного репозитория.")
    commit = api(token, "git/commits/" + commit_sha)
    tree_sha = commit.get("tree", {}).get("sha")
    if not isinstance(tree_sha, str) or len(tree_sha) != 40:
        raise RuntimeError("В коммите отсутствует Git tree.")
    tree = api(token, "git/trees/" + tree_sha + "?recursive=1")
    if tree.get("truncated"):
        raise RuntimeError("Дерево репозитория слишком велико для безопасной загрузки одним проходом.")
    entries = tree.get("tree")
    if not isinstance(entries, list):
        raise RuntimeError("GitHub вернул некорректное дерево исходников.")
    total = 0
    files = []
    for item in entries:
        if item.get("type") == "tree":
            continue
        if item.get("type") != "blob" or item.get("mode") not in ("100644", "100755"):
            raise RuntimeError("В исходниках найден неподдерживаемый тип Git-объекта.")
        name = item.get("path", "")
        path = pathlib.PurePosixPath(name)
        if not name or path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
            raise RuntimeError("В исходниках найден небезопасный путь.")
        size = item.get("size")
        sha = item.get("sha")
        if not isinstance(size, int) or size < 0 or size > MAX_FILE or not isinstance(sha, str):
            raise RuntimeError("Размер или идентификатор файла некорректен: " + name)
        total += size
        if total > MAX_TOTAL:
            raise RuntimeError("Общий размер исходников превышает безопасный лимит 120 MiB.")
        files.append((name, sha, size, item["mode"]))
    if not files:
        raise RuntimeError("GitHub вернул пустой репозиторий.")
    DEST.mkdir(mode=0o700, parents=True, exist_ok=False)
    for index, (name, sha, size, mode) in enumerate(files, 1):
        blob = api(token, "git/blobs/" + sha)
        if blob.get("encoding") != "base64" or not isinstance(blob.get("content"), str):
            raise RuntimeError("GitHub не вернул содержимое файла: " + name)
        try:
            data = base64.b64decode("".join(blob["content"].split()), validate=True)
        except Exception as exc:
            raise RuntimeError("Некорректное base64-содержимое: " + name) from exc
        if len(data) != size:
            raise RuntimeError("Размер файла не совпадает с Git tree: " + name)
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if actual != sha:
            raise RuntimeError("Git blob SHA не совпал: " + name)
        target = DEST.joinpath(*pathlib.PurePosixPath(name).parts)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o755 if mode == "100755" else 0o644)
        print(f"Получено {index}/{len(files)}: {name}")
    required = ("installer/install.sh", "server/domain-config.sh",
                "installer/preflight.sh", "auth/github-backups.py")
    for name in required:
        if not (DEST / name).is_file():
            raise RuntimeError("В репозитории отсутствует обязательный файл: " + name)
    (DEST / ".tsf-bootstrap-commit").write_text(commit_sha + "\n", encoding="ascii")
    (DEST / ".tsf-bootstrap-commit").chmod(0o600)
    print("\nИсходники получены и проверены.")
    print("Commit: " + commit_sha)

try:
    main()
except Exception as exc:
    print("Ошибка получения исходников: " + str(exc), file=sys.stderr)
    sys.exit(1)
PY

echo
echo "Запускается основной установщик TSF Connect."
export TSF_BOOTSTRAP_SOURCE="$WORK/source"
bash "$WORK/source/installer/install.sh" "${1:-}"
