"""Core logic: user secrets, config generation, proxy reload."""

import logging
import os
import secrets
import time

import docker
import redis.asyncio as aioredis

log = logging.getLogger(__name__)

PROXY_HOST = os.environ["PROXY_HOST"]
PROXY_PORT = int(os.environ.get("PROXY_PORT", 443))
TLS_DOMAIN = os.environ.get("TLS_DOMAIN", "www.google.com")
AD_TAG = os.environ.get("AD_TAG", "")
CONFIG_PATH = "/proxy-config/config.py"


class ProxyManager:
    def __init__(self, redis_url: str):
        self.redis: aioredis.Redis = aioredis.from_url(redis_url, decode_responses=False)
        self._docker: docker.DockerClient | None = None

    async def init(self):
        await self.redis.ping()
        self._docker = docker.from_env()
        log.info("ProxyManager ready")

    # ── user management ───────────────────────────────────────────────────────

    async def allow(self, user_id: str) -> tuple[bool, str]:
        """Grant access. Returns (created, secret_hex). created=False if already exists."""
        existing = await self.redis.hget("users", user_id)
        if existing:
            return False, existing.decode()

        secret = secrets.token_hex(16)
        await self.redis.hset("users", user_id, secret)
        await self._write_config_and_reload()
        return True, secret

    async def revoke(self, user_id: str) -> bool:
        """Revoke access. Returns True if user existed."""
        deleted = await self.redis.hdel("users", user_id)
        if deleted:
            await self._write_config_and_reload()
        return bool(deleted)

    async def get_secret(self, user_id: str) -> str | None:
        raw = await self.redis.hget("users", user_id)
        return raw.decode() if raw else None

    async def list_users(self) -> dict[str, str]:
        raw = await self.redis.hgetall("users")
        return {k.decode(): v.decode() for k, v in raw.items()}

    # ── link building ─────────────────────────────────────────────────────────

    def build_link(self, secret_hex: str) -> str:
        domain_hex = TLS_DOMAIN.encode().hex()
        tls_secret = f"ee{domain_hex}{secret_hex}"
        return f"https://t.me/proxy?server={PROXY_HOST}&port={PROXY_PORT}&secret={tls_secret}"

    async def get_link(self, user_id: str) -> str | None:
        secret = await self.get_secret(user_id)
        return self.build_link(secret) if secret else None

    # ── config & reload ───────────────────────────────────────────────────────

    async def _write_config_and_reload(self):
        users = await self.list_users()

        domain_hex = TLS_DOMAIN.encode().hex()
        users_repr = "{\n"
        for uid, secret in users.items():
            # mtprotoproxy expects the full secret including ee+domain prefix
            full_secret = f"ee{domain_hex}{secret}"
            users_repr += f'    "{uid}": bytes.fromhex("{full_secret}"),\n'
        users_repr += "}"

        ad_line = f'AD_TAG = bytes.fromhex("{AD_TAG}")' if AD_TAG else "AD_TAG = b''"

        config = (
            f"PORT = 443\n"
            f"USERS = {users_repr}\n"
            f"{ad_line}\n"
            f'TLS_DOMAIN = "{TLS_DOMAIN}"\n'
            f"# Generated at {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n"
        )

        with open(CONFIG_PATH, "w") as f:
            f.write(config)

        log.info("Config written: %d users", len(users))
        self._restart_proxy()

    def _restart_proxy(self):
        try:
            container = self._docker.containers.get("mtproxy")
            container.restart(timeout=5)
            log.info("mtproxy restarted")
        except Exception as e:
            log.warning("Could not restart mtproxy: %s", e)
