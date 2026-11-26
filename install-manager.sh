#!/usr/bin/env bash
# TSF Connect — first-run bootstrap. Installs only the standalone manager.
set -Eeuo pipefail

fail() { printf 'ОШИБКА: %s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || fail "Запустите от root: sudo bash install-manager.sh"
[[ -r /etc/os-release ]] || fail "Не удалось определить ОС."
. /etc/os-release
[[ "${ID:-}" == ubuntu && "${VERSION_ID:-}" == 24.04 ]] || fail "Поддерживается Ubuntu 24.04 LTS."
[[ "$(dpkg --print-architecture)" == amd64 ]] || fail "Поддерживается архитектура amd64."
command -v python3 >/dev/null 2>&1 || fail "Требуется Python 3."
command -v systemctl >/dev/null 2>&1 || fail "Требуется systemd."

if ! command -v qrencode >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-upgrade --no-install-recommends qrencode
fi

STATE=/var/lib/tsf-connect-manager
LIB=/usr/local/lib/tsf-connect-manager
LINK=/usr/local/sbin/tsf-connect
[[ ! -L "$STATE" && ! -L "$LIB" ]] || fail "Каталог менеджера является символической ссылкой; установка остановлена."
install -d -o root -g root -m 0700 "$STATE"
install -d -o root -g root -m 0755 "$LIB"
[[ "$(stat -c '%U:%G:%a' "$STATE")" == "root:root:700" ]] || fail "Небезопасные права каталога состояния менеджера."
[[ "$(stat -c '%U:%G:%a' "$LIB")" == "root:root:755" ]] || fail "Небезопасные права каталога менеджера."

if [[ -e "$LINK" || -L "$LINK" ]]; then
  [[ -L "$LINK" && "$(readlink -f "$LINK")" == "$LIB/manager.py" ]] ||
    fail "Путь $LINK уже занят; существующая команда не будет заменена."
fi

python3 - "$STATE/github-token" "$LIB/manager.py" <<'PY'
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
REF = "work/manager-first-bootstrap"
CLIENT_ID = "Iv23liiXhUA7P0zNBVmn"
API = "https://api.github.com"
DEVICE_CODE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"
DEVICE_URL = "https://github.com/login/device"
TOKEN_PATH = pathlib.Path(sys.argv[1])
MANAGER_PATH = pathlib.Path(sys.argv[2])

def request(url, method="GET", data=None, token=None, accept="application/vnd.github+json"):
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "TSF-Connect-Manager-Bootstrap"}
    if token:
        headers["Authorization"] = "Bearer " + token
    payload = None
    if data is not None:
        payload = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read(2 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", "replace")
        raise RuntimeError(f"GitHub HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Не удалось подключиться к GitHub.") from exc
    try:
        return json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("GitHub вернул некорректный ответ.") from exc

def main():
    token = None
    if TOKEN_PATH.exists() and not TOKEN_PATH.is_symlink():
        info = TOKEN_PATH.lstat()
        if info.st_uid == 0 and info.st_gid == 0 and (info.st_mode & 0o777) == 0o600:
            candidate = TOKEN_PATH.read_text(encoding="utf-8").strip()
            if candidate:
                try:
                    saved_repo = request(f"{API}/repos/{OWNER}/{REPO}", token=candidate)
                except RuntimeError as exc:
                    if not any(f"HTTP {code}" in str(exc) for code in (401, 404)):
                        raise
                    saved_repo = {}
                if saved_repo.get("full_name", "").lower() == f"{OWNER}/{REPO}".lower() and saved_repo.get("private") is True:
                    token = candidate

    if token is None:
        print("\nПервичная настройка менеджера TSF Connect.")
        print("Сейчас будет выполнена однократная авторизация GitHub Device Flow.")
        device = request(DEVICE_CODE_URL, "POST", {"client_id": CLIENT_ID, "scope": "repo"},
                         accept="application/json")
        if device.get("error"):
            raise RuntimeError("GitHub Device Flow: " + str(device.get("error_description") or device["error"]))
        code = device.get("device_code")
        user_code = device.get("user_code")
        verify = device.get("verification_uri")
        if not isinstance(code, str) or not code or not isinstance(user_code, str) or verify != DEVICE_URL:
            raise RuntimeError("GitHub вернул некорректные параметры Device Flow.")
        subprocess.run(["qrencode", "-t", "ANSIUTF8", "-m", "2", verify],
                       check=True, stdin=subprocess.DEVNULL)
        print("\nОткройте " + verify)
        print("Одноразовый код: " + user_code)
        print("Подтвердите доступ к приватному репозиторию SCORP365/TSF-Connect.")
        interval = max(5, int(device.get("interval", 5)))
        deadline = time.monotonic() + int(device.get("expires_in", 900))
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
            token = result.get("access_token")
            if not isinstance(token, str) or not token or result.get("token_type", "").lower() != "bearer":
                raise RuntimeError("GitHub не выдал токен доступа.")
            break
        if not token:
            raise RuntimeError("Время действия одноразового кода истекло.")
        repository = request(f"{API}/repos/{OWNER}/{REPO}", token=token)
        if repository.get("full_name", "").lower() != f"{OWNER}/{REPO}".lower() or repository.get("private") is not True:
            raise RuntimeError("Токен не подтвердил доступ к приватному репозиторию TSF Connect.")
        token_tmp = TOKEN_PATH.with_name("github-token.tmp")
        fd = os.open(token_tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(token + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chown(token_tmp, 0, 0)
        os.chmod(token_tmp, 0o600)
        os.replace(token_tmp, TOKEN_PATH)

    item = request(f"{API}/repos/{OWNER}/{REPO}/contents/manager/manager.py?ref={urllib.parse.quote(REF)}", token=token)
    if item.get("encoding") != "base64" or not isinstance(item.get("content"), str):
        raise RuntimeError("Не удалось получить отдельный файл менеджера из GitHub.")
    raw = base64.b64decode("".join(item["content"].split()), validate=True)
    expected = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if expected != item.get("sha") or not raw.startswith(b"#!/usr/bin/env python3"):
        raise RuntimeError("Файл менеджера не прошёл проверку Git SHA.")
    manager_tmp = MANAGER_PATH.with_name("manager.py.new")
    fd = os.open(manager_tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o750)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.chown(manager_tmp, 0, 0)
    os.chmod(manager_tmp, 0o750)
    os.replace(manager_tmp, MANAGER_PATH)
    print("\nМенеджер получен отдельно; остальные файлы проекта не загружались.")
    print("Авторизация сохранена в защищённом системном каталоге.")
try:
    main()
except Exception as exc:
    print("ОШИБКА: " + str(exc), file=sys.stderr)
    sys.exit(1)
PY

ln -sfn "$LIB/manager.py" "$LINK"
chmod 0750 "$LIB/manager.py"
chown root:root "$LIB/manager.py" "$STATE/github-token"
chmod 0600 "$STATE/github-token"
echo
echo "Установлен только менеджер TSF Connect."
echo "Для открытия меню выполните: tsf-connect"
