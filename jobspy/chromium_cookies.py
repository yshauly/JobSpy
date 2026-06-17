from __future__ import annotations

import base64
import ctypes
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ctypes import wintypes


LINKEDIN_AUTH_COOKIE_NAMES = ("li_at", "JSESSIONID")
BUILTIN_LINKEDIN_AUTH_COOKIES = {
    "li_at": "AQEDASTFbTYAcQkzAAABnqyPSXcAAAGe0JvNd00APWMDI_vgDzCbsWJdcpRzn1RGSrSJ3OpfIzuh3H3IQdodC1IDBDSQpatSXWh1OeSsDrkqLeLelxJduObAkc4GI77fiynpR_JNChSUY_52QjEk3vr_",
    "JSESSIONID": '"ajax:6671628041215731282"',
}
LINKEDIN_COOKIE_HEADER_ENV = "LINKEDIN_COOKIE_HEADER"
LINKEDIN_COOKIE_FILE_ENV = "LINKEDIN_COOKIE_FILE"
LINKEDIN_ENV_COOKIE_NAMES = {
    "li_at": "LINKEDIN_LI_AT",
    "JSESSIONID": "LINKEDIN_JSESSIONID",
}
SET_COOKIE_ATTRIBUTES = {
    "domain",
    "path",
    "expires",
    "max-age",
    "secure",
    "httponly",
    "samesite",
    "priority",
    "partitioned",
}
WORKSPACE_CHROMIUM_DIR_PATTERNS = (
    "jobspy-chrome-*",
    "jobspy-edge-*",
    "tmpchrome-*",
)


@dataclass(frozen=True)
class ChromiumProfileCookieStore:
    browser_name: str
    user_data_dir: Path
    profile_dir: Path
    cookie_db_path: Path


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def resolve_linkedin_auth_context(
    explicit_cookies: dict[str, str] | None = None,
    *,
    builtin_cookie_loader: Callable[[], dict[str, str]] | None = None,
    browser_cookie_loader: Callable[[], tuple[dict[str, str], str | None]] | None = None,
) -> tuple[dict[str, str], str]:
    normalized_explicit_cookies = _normalize_cookie_map(explicit_cookies)
    if normalized_explicit_cookies:
        return normalized_explicit_cookies, "explicit"

    env_cookies = load_linkedin_env_cookies()
    if env_cookies:
        return env_cookies, "env"

    cookie_loader = browser_cookie_loader or load_linkedin_chromium_cookies
    browser_cookies, browser_source = cookie_loader()
    if browser_cookies:
        return browser_cookies, browser_source or "browser"

    hardcoded_cookies = (
        builtin_cookie_loader or load_linkedin_builtin_cookies
    )()
    if hardcoded_cookies:
        return hardcoded_cookies, "hardcoded"

    return {}, "guest-only"


def load_linkedin_env_cookies() -> dict[str, str]:
    cookies: dict[str, str] = {}

    cookie_file_path = (os.getenv(LINKEDIN_COOKIE_FILE_ENV) or "").strip()
    if cookie_file_path:
        cookie_file = Path(cookie_file_path).expanduser()
        if cookie_file.exists():
            _merge_cookie_text(
                cookies,
                cookie_file.read_text(encoding="utf-8"),
            )

    _merge_cookie_text(cookies, os.getenv(LINKEDIN_COOKIE_HEADER_ENV))

    for cookie_name, env_name in LINKEDIN_ENV_COOKIE_NAMES.items():
        cookie_value = (os.getenv(env_name) or "").strip()
        if cookie_value:
            cookies[cookie_name] = cookie_value

    return _normalize_cookie_map(cookies)


def load_linkedin_builtin_cookies() -> dict[str, str]:
    return _normalize_cookie_map(BUILTIN_LINKEDIN_AUTH_COOKIES)


def load_linkedin_chromium_cookies() -> tuple[dict[str, str], str | None]:
    if os.name != "nt":
        return {}, None

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except Exception:
        return {}, None

    for cookie_store in _discover_chromium_profile_cookie_stores():
        cookies = _load_linkedin_cookies_from_store(cookie_store, aesgcm_cls=AESGCM)
        if cookies:
            return (
                cookies,
                f"browser:{cookie_store.browser_name}/{cookie_store.profile_dir.name}",
            )

    return {}, None


def _discover_chromium_profile_cookie_stores() -> list[ChromiumProfileCookieStore]:
    user_data_roots = _discover_chromium_user_data_roots()
    cookie_stores: list[ChromiumProfileCookieStore] = []

    for browser_name, user_data_dir in user_data_roots:
        if not _path_exists(user_data_dir):
            continue

        for profile_dir in _discover_chromium_profile_dirs(user_data_dir):
            for cookie_db_path in (
                profile_dir / "Network" / "Cookies",
                profile_dir / "Cookies",
            ):
                if not _path_exists(cookie_db_path):
                    continue
                cookie_stores.append(
                    ChromiumProfileCookieStore(
                        browser_name=browser_name,
                        user_data_dir=user_data_dir,
                        profile_dir=profile_dir,
                        cookie_db_path=cookie_db_path,
                    )
                )
                break

    return sorted(
        cookie_stores,
        key=lambda store: _get_mtime(store.cookie_db_path),
        reverse=True,
    )


def _discover_chromium_user_data_roots() -> list[tuple[str, Path]]:
    local_app_data = Path(os.getenv("LOCALAPPDATA", ""))
    candidate_roots: list[tuple[str, Path]] = [
        ("chrome", local_app_data / "Google" / "Chrome" / "User Data"),
        ("edge", local_app_data / "Microsoft" / "Edge" / "User Data"),
        ("brave", local_app_data / "BraveSoftware" / "Brave-Browser" / "User Data"),
        ("chromium", local_app_data / "Chromium" / "User Data"),
    ]
    candidate_roots.extend(_discover_workspace_chromium_user_data_roots())

    discovered_roots: list[tuple[str, Path]] = []
    seen_roots: set[str] = set()
    for browser_name, user_data_dir in candidate_roots:
        normalized_user_data_dir = str(user_data_dir).lower()
        if not normalized_user_data_dir or normalized_user_data_dir in seen_roots:
            continue
        seen_roots.add(normalized_user_data_dir)
        discovered_roots.append((browser_name, user_data_dir))

    return discovered_roots


def _discover_workspace_chromium_user_data_roots() -> list[tuple[str, Path]]:
    try:
        workspace_root = Path.cwd()
    except Exception:
        return []

    discovered_roots: list[tuple[str, Path]] = []
    for pattern in WORKSPACE_CHROMIUM_DIR_PATTERNS:
        try:
            matching_dirs = sorted(workspace_root.glob(pattern))
        except Exception:
            continue

        for user_data_dir in matching_dirs:
            if not user_data_dir.is_dir():
                continue
            discovered_roots.append(("jobspy-chrome", user_data_dir))

    return discovered_roots


def _discover_chromium_profile_dirs(user_data_dir: Path) -> list[Path]:
    profile_dirs: list[Path] = []
    seen_profile_dirs: set[str] = set()

    def add_profile_dir(profile_dir: Path) -> None:
        normalized_profile_dir = str(profile_dir).lower()
        if normalized_profile_dir in seen_profile_dirs:
            return
        seen_profile_dirs.add(normalized_profile_dir)
        profile_dirs.append(profile_dir)

    for profile_name in ("Default", "Profile 1", "Profile 2", "Profile 3"):
        profile_dir = user_data_dir / profile_name
        if _path_exists(profile_dir):
            add_profile_dir(profile_dir)

    try:
        profile_entries = list(user_data_dir.iterdir())
    except Exception:
        profile_entries = []

    for profile_dir in profile_entries:
        if not profile_dir.is_dir():
            continue
        if profile_dir.name != "Default" and not profile_dir.name.startswith("Profile "):
            continue
        add_profile_dir(profile_dir)

    return profile_dirs


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except Exception:
        return False


def _get_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except Exception:
        return 0.0


def _load_linkedin_cookies_from_store(
    cookie_store: ChromiumProfileCookieStore,
    *,
    aesgcm_cls: Any,
) -> dict[str, str]:
    master_key = _load_chromium_master_key(cookie_store.user_data_dir)
    copied_cookie_db_path = _copy_chromium_cookie_database(cookie_store.cookie_db_path)
    if copied_cookie_db_path is None:
        return {}

    try:
        rows = _read_linkedin_cookie_rows(copied_cookie_db_path)
    finally:
        shutil.rmtree(copied_cookie_db_path.parent, ignore_errors=True)

    cookies: dict[str, str] = {}
    for row in rows:
        cookie_name = row["name"]
        cookie_value = row["value"]
        if not cookie_value:
            cookie_value = _decrypt_chromium_cookie_value(
                row["encrypted_value"],
                master_key=master_key,
                aesgcm_cls=aesgcm_cls,
            )

        if cookie_value and cookie_name not in cookies:
            cookies[cookie_name] = cookie_value

        if all(cookies.get(name) for name in LINKEDIN_AUTH_COOKIE_NAMES):
            break

    return cookies


def _copy_chromium_cookie_database(cookie_db_path: Path) -> Path | None:
    temp_dir = Path(tempfile.mkdtemp(prefix="jobspy-chromium-cookies-"))
    copied_cookie_db_path = temp_dir / cookie_db_path.name

    copied = _copy_file(cookie_db_path, copied_cookie_db_path)
    if not copied:
        copied = _copy_file_with_esentutl(cookie_db_path, copied_cookie_db_path)

    if not copied:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None

    for companion_suffix in ("-wal", "-shm"):
        companion_source_path = Path(f"{cookie_db_path}{companion_suffix}")
        companion_dest_path = Path(f"{copied_cookie_db_path}{companion_suffix}")
        if companion_source_path.exists():
            _copy_file(companion_source_path, companion_dest_path)

    return copied_cookie_db_path


def _copy_file(source_path: Path, dest_path: Path) -> bool:
    try:
        shutil.copy2(source_path, dest_path)
    except Exception:
        return False

    return dest_path.exists()


def _copy_file_with_esentutl(source_path: Path, dest_path: Path) -> bool:
    try:
        result = subprocess.run(
            ["esentutl", "/y", str(source_path), "/d", str(dest_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception:
        return False

    return result.returncode == 0 and dest_path.exists()


def _read_linkedin_cookie_rows(copied_cookie_db_path: Path) -> list[dict[str, Any]]:
    query = """
        SELECT
            name,
            value,
            encrypted_value,
            host_key,
            path,
            creation_utc,
            last_access_utc
        FROM cookies
        WHERE host_key LIKE '%linkedin.com%'
          AND name IN (?, ?)
        ORDER BY last_access_utc DESC, creation_utc DESC
    """

    with sqlite3.connect(copied_cookie_db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(query, LINKEDIN_AUTH_COOKIE_NAMES)
        rows = cursor.fetchall()

    return [
        {
            "name": row[0],
            "value": row[1],
            "encrypted_value": row[2],
            "host_key": row[3],
            "path": row[4],
            "creation_utc": row[5],
            "last_access_utc": row[6],
        }
        for row in rows
    ]


def _load_chromium_master_key(user_data_dir: Path) -> bytes | None:
    local_state_path = user_data_dir / "Local State"
    if not local_state_path.exists():
        return None

    try:
        local_state = json.loads(local_state_path.read_text(encoding="utf-8"))
        encrypted_key_b64 = local_state["os_crypt"]["encrypted_key"]
        encrypted_key = base64.b64decode(encrypted_key_b64)
    except Exception:
        return None

    if encrypted_key.startswith(b"DPAPI"):
        encrypted_key = encrypted_key[5:]

    return _dpapi_unprotect(encrypted_key)


def _decrypt_chromium_cookie_value(
    encrypted_value: bytes | bytearray | memoryview | None,
    *,
    master_key: bytes | None,
    aesgcm_cls: Any,
) -> str | None:
    if encrypted_value is None:
        return None

    if isinstance(encrypted_value, memoryview):
        encrypted_value = encrypted_value.tobytes()
    elif isinstance(encrypted_value, bytearray):
        encrypted_value = bytes(encrypted_value)

    if not encrypted_value:
        return None

    if encrypted_value.startswith((b"v10", b"v11", b"v20")):
        if not master_key:
            return None

        nonce = encrypted_value[3:15]
        ciphertext = encrypted_value[15:]
        try:
            decrypted_value = aesgcm_cls(master_key).decrypt(nonce, ciphertext, None)
        except Exception:
            return None
        return decrypted_value.decode("utf-8", errors="ignore")

    decrypted_value = _dpapi_unprotect(encrypted_value)
    if decrypted_value is None:
        return None

    return decrypted_value.decode("utf-8", errors="ignore")


def _dpapi_unprotect(encrypted_bytes: bytes) -> bytes | None:
    if not encrypted_bytes:
        return None

    buffer = ctypes.create_string_buffer(encrypted_bytes, len(encrypted_bytes))
    input_blob = DATA_BLOB(
        cbData=len(encrypted_bytes),
        pbData=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)),
    )
    output_blob = DATA_BLOB()

    crypt_unprotect_data = ctypes.windll.crypt32.CryptUnprotectData
    crypt_unprotect_data.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    crypt_unprotect_data.restype = wintypes.BOOL

    if not crypt_unprotect_data(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    ):
        return None

    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)


def _normalize_cookie_map(cookies: dict[str, str] | None) -> dict[str, str]:
    normalized_cookies: dict[str, str] = {}
    if not cookies:
        return normalized_cookies

    for cookie_name, cookie_value in cookies.items():
        normalized_name = (cookie_name or "").strip()
        normalized_value = (cookie_value or "").strip()
        if normalized_name and normalized_value:
            normalized_cookies[normalized_name] = normalized_value

    return normalized_cookies


def _merge_cookie_text(cookies: dict[str, str], cookie_text: str | None) -> None:
    if not cookie_text:
        return

    for line in cookie_text.splitlines():
        line = line.strip()
        if not line:
            continue

        for cookie_part in line.split(";"):
            cookie_part = cookie_part.strip()
            if not cookie_part or "=" not in cookie_part:
                continue

            cookie_name, cookie_value = _parse_cookie_assignment(cookie_part)
            if cookie_name.lower() in SET_COOKIE_ATTRIBUTES:
                continue
            cookies[cookie_name] = cookie_value


def _parse_cookie_assignment(raw_cookie: str) -> tuple[str, str]:
    cookie_name, cookie_value = raw_cookie.split("=", 1)
    return cookie_name.strip(), cookie_value.strip()
