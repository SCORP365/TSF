#!/usr/bin/env python3
"""GitHub App Device Flow helper for TSF Connect bootstrap.

This module only obtains a short-lived token in memory. It does not download,
extract, or execute private repository code.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

CLIENT_ID = "Iv23liiXhUA7P0zNBVmn"
DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
VERIFICATION_URI = "https://github.com/login/device"
USER_AGENT = "TSF-Connect-Bootstrap/0.1"


class DeviceFlowError(RuntimeError):
    """A safe, user-displayable Device Flow failure."""


@dataclass(frozen=True)
class DeviceAuthorization:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


def _post_form(url: str, fields: dict[str, str]) -> dict:
    body = urllib.parse.urlencode(fields).encode("ascii")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read(64 * 1024)
    except urllib.error.HTTPError as exc:
        # Do not include response bodies or request details in user-visible errors.
        raise DeviceFlowError(f"GitHub returned HTTP {exc.code}.") from None
    except (urllib.error.URLError, TimeoutError):
        raise DeviceFlowError("Cannot reach GitHub. Check the network and try again.") from None

    try:
        result = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise DeviceFlowError("GitHub returned an invalid response.") from None
    if not isinstance(result, dict):
        raise DeviceFlowError("GitHub returned an invalid response.")
    return result


def _show_qr(uri: str) -> None:
    """Render a terminal QR code using the OS qrencode utility."""
    executable = shutil.which("qrencode")
    if not executable:
        raise DeviceFlowError(
            "The qrencode utility is required to display the login QR code. "
            "Install the Ubuntu package 'qrencode', then run bootstrap again."
        )
    try:
        subprocess.run(
            [executable, "-t", "ANSIUTF8", "-m", "2", uri],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=None,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        raise DeviceFlowError("Could not render the GitHub login QR code.") from None


def begin_device_authorization() -> DeviceAuthorization:
    response = _post_form(
        DEVICE_CODE_URL,
        {"client_id": CLIENT_ID},
    )
    if response.get("error"):
        if response["error"] == "device_flow_disabled":
            raise DeviceFlowError("GitHub Device Flow is not enabled for the TSF Connect Installer app.")
        raise DeviceFlowError("GitHub refused to start device authorization.")

    try:
        device_code = response["device_code"]
        user_code = response["user_code"]
        verification_uri = response.get("verification_uri", VERIFICATION_URI)
        expires_in = int(response["expires_in"])
        interval = max(1, int(response.get("interval", 5)))
    except (KeyError, TypeError, ValueError):
        raise DeviceFlowError("GitHub returned incomplete device authorization data.") from None

    if (
        not isinstance(device_code, str) or not device_code
        or not isinstance(user_code, str) or not user_code
        or verification_uri != VERIFICATION_URI
        or not 60 <= expires_in <= 1800
        or not 1 <= interval <= 60
    ):
        raise DeviceFlowError("GitHub returned unexpected device authorization data.")

    return DeviceAuthorization(device_code, user_code, verification_uri, expires_in, interval)


def wait_for_access_token(
    authorization: DeviceAuthorization,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    deadline = time.monotonic() + authorization.expires_in
    interval = authorization.interval

    while time.monotonic() < deadline:
        sleep(min(interval, max(0, deadline - time.monotonic())))
        response = _post_form(
            ACCESS_TOKEN_URL,
            {
                "client_id": CLIENT_ID,
                "device_code": authorization.device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )

        error = response.get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        if error == "expired_token":
            raise DeviceFlowError("The GitHub login code expired. Start again.")
        if error == "access_denied":
            raise DeviceFlowError("GitHub access was denied.")
        if error:
            raise DeviceFlowError("GitHub device authorization failed.")

        token = response.get("access_token")
        token_type = response.get("token_type", "")
        if not isinstance(token, str) or not token or token_type.lower() != "bearer":
            raise DeviceFlowError("GitHub returned an invalid access token response.")
        return token

    raise DeviceFlowError("The GitHub login code expired. Start again.")


def authorize() -> str:
    authorization = begin_device_authorization()
    print("\nGitHub authorization for TSF Connect")
    _show_qr(authorization.verification_uri)
    print(f"\nOpen: {authorization.verification_uri}")
    print(f"One-time code: {authorization.user_code}")
    print("Approve access for the TSF Connect Installer application.")
    print("Waiting for approval; the token will remain in memory only.\n")
    return wait_for_access_token(authorization)


if __name__ == "__main__":
    try:
        token = authorize()
        # Do not print, persist, or pass the token through argv/environment.
        # The next bootstrap stage will consume it in-process.
        del token
        print("GitHub authorization completed. No token was saved.")
        print("Private source retrieval is not enabled in this development build.")
    except DeviceFlowError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
