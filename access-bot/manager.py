"""Core logic: user secrets, config generation, proxy reload."""

import logging
import os
import re
import secrets
import time

import docker
import redis.asyncio as aioredis

log = logging.getLogger(__name__)

PROXY_HOST = os.environ["PROXY_HOST"]
PROXY_PORT = int(os.environ.get("PROXY_PORT", 2083))
PROXY_PORT_NOAD = int(os.environ.get("PROXY_PORT_NOAD", 2084))
TLS_DOMAIN = os.environ.get("TLS_DOMAIN", "www.google.com")
AD_TAG = os.environ.get("AD_TAG", "")
PROXY_SECRET_MODE = os.environ.get("PROXY_SECRET_MODE", "dd").lower()
DEFAULT_CONN_LIMIT = int(os.environ.get("DEFAULT_CONN_LIMIT", 3))

_CONFIG_PATH = {
    False: "/proxy-config/config.py",
    True:  "/proxy-config-noad/config.py",
}
_CONTAINER_NAME = {
    False: "mtproxy",
    True:  "mtproxy-noad",
}
_REDIS_KEY = {
    False: "users",
    True:  "users_noad",
}
_REDIS_LIMITS_KEY = "conn_limits"  # hash: {user_id: int}


class ProxyManager:
    def __init__(self, redis_url: str):
        self.redis: aioredis.Redis = aioredis.from_url(redis_url, decode_responses=False)
        self._docker: docker.DockerClient | None = None

    async def init(self):
        await self.redis.ping()
        self._docker = docker.from_env()
        log.info("ProxyManager ready")

    # ── user management ───────────────────────────────────────────────────────

    async def allow(self, user_id: str, no_ad: bool = False) -> tuple[bool, str]:
        """Grant access. Returns (created, secret_hex). created=False if already exists.

        no_ad=True puts the user on the ad-free proxy instance (PROXY_PORT_NOAD).
        A user can only belong to one tier at a time.
        """
        target_key = _REDIS_KEY[no_ad]
        other_key  = _REDIS_KEY[not no_ad]

        existing = await self.redis.hget(target_key, user_id)
        if existing:
            return False, existing.decode()

        # Already in the other tier — return their existing link without moving
        other = await self.redis.hget(other_key, user_id)
        if other:
            return False, other.decode()

        secret = secrets.token_hex(16)
        await self.redis.hset(target_key, user_id, secret)
        await self._write_config_and_reload(no_ad)
        return True, secret

    async def move(self, user_id: str, no_ad: bool) -> tuple[bool, str]:
        """Move user to a different tier. Returns (moved, new_link).

        moved=False if user was already in the requested tier or doesn't exist.
        """
        target_key = _REDIS_KEY[no_ad]
        source_key = _REDIS_KEY[not no_ad]

        if await self.redis.hexists(target_key, user_id):
            existing = await self.redis.hget(target_key, user_id)
            return False, self.build_link(existing.decode(), no_ad)

        await self.redis.hdel(source_key, user_id)
        secret = secrets.token_hex(16)
        await self.redis.hset(target_key, user_id, secret)
        await self._write_config_and_reload(not no_ad)
        await self._write_config_and_reload(no_ad)
        return True, self.build_link(secret, no_ad)

    async def revoke(self, user_id: str) -> bool:
        """Revoke access from either tier. Returns True if user existed."""
        deleted_ad   = await self.redis.hdel(_REDIS_KEY[False], user_id)
        deleted_noad = await self.redis.hdel(_REDIS_KEY[True],  user_id)
        if deleted_ad:
            await self._write_config_and_reload(False)
        if deleted_noad:
            await self._write_config_and_reload(True)
        return bool(deleted_ad or deleted_noad)

    async def get_secret(self, user_id: str) -> tuple[str, bool] | None:
        """Returns (secret_hex, no_ad) or None if user not found."""
        for no_ad in (False, True):
            raw = await self.redis.hget(_REDIS_KEY[no_ad], user_id)
            if raw:
                return raw.decode(), no_ad
        return None

    async def list_users(self) -> dict[str, tuple[str, bool]]:
        """Returns {user_id: (secret_hex, no_ad)}."""
        result: dict[str, tuple[str, bool]] = {}
        for no_ad in (False, True):
            raw = await self.redis.hgetall(_REDIS_KEY[no_ad])
            for k, v in raw.items():
                result[k.decode()] = (v.decode(), no_ad)
        return result

    # ── link building ─────────────────────────────────────────────────────────

    def build_link(self, secret_hex: str, no_ad: bool = False) -> str:
        port = PROXY_PORT_NOAD if no_ad else PROXY_PORT
        # dd-режим обычно более совместим с клиентами, ee можно включить через PROXY_SECRET_MODE=ee
        if PROXY_SECRET_MODE == "ee":
            domain_hex = TLS_DOMAIN.encode().hex()
            client_secret = f"ee{secret_hex}{domain_hex}"
        else:
            client_secret = f"dd{secret_hex}"
        return f"https://t.me/proxy?server={PROXY_HOST}&port={port}&secret={client_secret}"

    async def get_link(self, user_id: str) -> str | None:
        info = await self.get_secret(user_id)
        return self.build_link(*info) if info else None

    # ── connection limits ─────────────────────────────────────────────────────

    @property
    def default_conn_limit(self) -> int:
        return DEFAULT_CONN_LIMIT

    async def set_conn_limit(self, user_id: str, limit: int | None) -> None:
        """Set per-user connection limit. Pass None to remove override (use default)."""
        if limit is None:
            await self.redis.hdel(_REDIS_LIMITS_KEY, user_id)
        else:
            await self.redis.hset(_REDIS_LIMITS_KEY, user_id, str(limit))
        for no_ad in (False, True):
            if await self.redis.hexists(_REDIS_KEY[no_ad], user_id):
                await self._write_config_and_reload(no_ad)

    async def get_conn_limit(self, user_id: str) -> tuple[int, bool]:
        """Returns (effective_limit, is_custom). is_custom=True if per-user override exists."""
        raw = await self.redis.hget(_REDIS_LIMITS_KEY, user_id)
        if raw:
            return int(raw), True
        return DEFAULT_CONN_LIMIT, False

    # ── config & reload ───────────────────────────────────────────────────────

    async def _write_config_and_reload(self, no_ad: bool):
        raw = await self.redis.hgetall(_REDIS_KEY[no_ad])
        users = {k.decode(): v.decode() for k, v in raw.items()}

        raw_limits = await self.redis.hgetall(_REDIS_LIMITS_KEY)
        overrides = {k.decode(): int(v) for k, v in raw_limits.items()}

        users_repr = "{\n"
        for uid, secret in users.items():
            # mtprotoproxy ожидает в USERS только 16-байтный hex-секрет (без ee и без домена)
            users_repr += f'    "{uid}": "{secret}",\n'
        users_repr += "}"

        # mtprotoproxy calls bytes.fromhex(AD_TAG) internally — must be a plain hex string
        ad_line = f'AD_TAG = "{AD_TAG}"' if (AD_TAG and not no_ad) else 'AD_TAG = ""'

        config = (
            f"PORT = 443\n"
            f"USERS = {users_repr}\n"
            f"{ad_line}\n"
            f'TLS_DOMAIN = "{TLS_DOMAIN}"\n'
            f"METRICS_PORT = 8888\n"
            f"# Generated at {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n"
        )

        with open(_CONFIG_PATH[no_ad], "w") as f:
            f.write(config)

        label = "noad" if no_ad else "ad"
        log.info("Config written (%s): %d users", label, len(users))
        self._restart_proxy(no_ad)

    def _restart_proxy(self, no_ad: bool):
        container_name = _CONTAINER_NAME[no_ad]
        try:
            container = self._docker.containers.get(container_name)
            container.restart(timeout=5)
            log.info("%s restarted", container_name)
        except Exception as e:
            log.warning("Could not restart %s: %s", container_name, e)

    def fetch_active_conns(self, no_ad: bool) -> dict[str, int]:
        """Returns {user_id: curr_connects} from the proxy metrics endpoint."""
        try:
            container = self._docker.containers.get(_CONTAINER_NAME[no_ad])
            result = container.exec_run([
                "python3", "-c",
                "import urllib.request; print(urllib.request.urlopen('http://localhost:8888').read().decode())"
            ])
            if result.exit_code != 0:
                return {}
            conns: dict[str, int] = {}
            for m in re.finditer(
                r'mtprotoproxy_user_connects_curr\{user="([^"]+)"\}\s+(\d+)',
                result.output.decode()
            ):
                conns[m.group(1)] = int(m.group(2))
            return conns
        except Exception as e:
            log.warning("Could not fetch metrics from %s: %s", _CONTAINER_NAME[no_ad], e)
            return {}
