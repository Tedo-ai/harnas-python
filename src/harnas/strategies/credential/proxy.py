"""Credential proxy strategy."""

from __future__ import annotations

import copy
import fnmatch
import os
import re
from typing import Any
from urllib.parse import urlparse

from ... import hooks as global_hooks
from ...hooks import TurnFailed


class Proxy:
    HEADER_TOOLS = {"fetch_url"}
    CREDENTIAL_PATTERN = re.compile(r"\{credential\.([A-Za-z0-9_]+)\}")

    @classmethod
    def install(
        cls,
        session=None,
        credentials: dict[str, Any] | None = None,
        routes: list[dict[str, Any]] | None = None,
    ):
        instance = cls(credentials=credentials or {}, routes=routes or [])
        target_hooks = session.hooks if session is not None else global_hooks
        target_hooks.on("pre_tool_use", instance.on_pre_tool_use)
        return instance.on_pre_tool_use

    def __init__(self, credentials: dict[str, Any], routes: list[dict[str, Any]]) -> None:
        self._credentials = self._validate_credentials(credentials)
        self._routes = self._validate_routes(routes)
        self._consecutive_missing = 0

    def on_pre_tool_use(self, *, session, tool_use, **_: Any) -> dict[str, Any]:
        rewritten = copy.deepcopy(tool_use.payload.get("arguments") or {})
        changed = False
        for index, route in enumerate(self._routes):
            if not self._route_matches(route, tool_use):
                continue
            if route["tool"] not in self.HEADER_TOOLS:
                self._append_runtime_error(
                    session,
                    "credential_proxy_unsupported_tool",
                    f"credential/proxy route matched unsupported tool '{route['tool']}'",
                )
                return {"allow": False, "reason": "credential_proxy_unsupported_tool"}

            value, used, missing = self._resolve_template(route["inject"]["value"])
            if missing is not None:
                return self._missing_credential(session, route, missing)

            headers = self._string_dict(rewritten.get("headers") or {})
            headers[route["inject"]["key"]] = value
            rewritten["headers"] = headers
            changed = True
            self._consecutive_missing = 0
            self._append_annotation(session, route, index, used)
        if not changed:
            return {"allow": True}
        return {"allow": True, "arguments": rewritten}

    def _validate_credentials(self, credentials: dict[str, Any]) -> dict[str, dict[str, Any]]:
        if not isinstance(credentials, dict):
            raise ValueError("credential/proxy credentials must be an object")
        out: dict[str, dict[str, Any]] = {}
        for name, spec in credentials.items():
            if not isinstance(spec, dict):
                raise ValueError(f"credential {name!r} must be an object")
            source = str(spec.get("from") or "")
            if source not in {"env", "literal"}:
                raise ValueError(f"credential {name!r} has unsupported from: {source!r}")
            out[str(name)] = {
                "from": source,
                "name": spec.get("name"),
                "value": spec.get("value"),
            }
        return out

    def _validate_routes(self, routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(routes, list):
            raise ValueError("credential/proxy routes must be an array")
        return [self._validate_route(route, index) for index, route in enumerate(routes)]

    def _validate_route(self, route: dict[str, Any], index: int) -> dict[str, Any]:
        if not isinstance(route, dict):
            raise ValueError(f"credential/proxy route {index} must be an object")
        tool = str(route.get("tool") or "")
        if not tool:
            raise ValueError(f"credential/proxy route {index} missing tool")
        match = route.get("match") or {}
        inject = route.get("inject")
        if not isinstance(match, dict):
            raise ValueError(f"credential/proxy route {index} match must be an object")
        if not isinstance(inject, dict):
            raise ValueError(f"credential/proxy route {index} inject must be an object")
        if str(inject.get("into") or "") != "headers":
            raise ValueError(f"credential/proxy route {index} only supports inject.into=headers")
        key = str(inject.get("key") or "")
        value = str(inject.get("value") or "")
        if not key or not value:
            raise ValueError(f"credential/proxy route {index} missing inject key/value")
        matchers = sum(1 for key_name in ("url_host", "url_host_glob") if key_name in match)
        if matchers > 1:
            raise ValueError(f"credential/proxy route {index} may use only one URL matcher")
        return {
            "tool": tool,
            "match": match,
            "inject": {"into": "headers", "key": key, "value": value},
        }

    def _route_matches(self, route: dict[str, Any], tool_use) -> bool:
        if tool_use.payload.get("name") != route["tool"]:
            return False
        match = route["match"]
        if not match:
            return True
        host = self._url_host(tool_use.payload.get("arguments") or {})
        if "url_host" in match:
            return host == str(match["url_host"])
        if "url_host_glob" in match:
            return fnmatch.fnmatchcase(host or "", str(match["url_host_glob"]))
        return True

    def _url_host(self, args: dict[str, Any]) -> str | None:
        try:
            return urlparse(str(args.get("url") or "")).hostname
        except ValueError:
            return None

    def _resolve_template(self, template: str) -> tuple[str, list[str], str | None]:
        used: list[str] = []
        missing: str | None = None

        def replace(match: re.Match[str]) -> str:
            nonlocal missing
            name = match.group(1)
            value = self._resolve_credential(name)
            if value is None:
                missing = name
                return ""
            used.append(name)
            return value

        value = self.CREDENTIAL_PATTERN.sub(replace, template)
        return value, list(dict.fromkeys(used)), missing

    def _resolve_credential(self, name: str) -> str | None:
        spec = self._credentials.get(name)
        if spec is None:
            return None
        if spec["from"] == "literal":
            return None if spec.get("value") is None else str(spec["value"])
        if spec["from"] == "env":
            env_name = str(spec.get("name") or "")
            return os.environ.get(env_name)
        return None

    def _missing_credential(self, session, route: dict[str, Any], name: str) -> dict[str, Any]:
        self._consecutive_missing += 1
        if self._consecutive_missing >= 3:
            self._append_runtime_error(
                session,
                "credential_proxy_missing_persistent",
                f"credential '{name}' is persistently unavailable",
            )
            raise TurnFailed("credential_proxy_missing_persistent")
        return {
            "allow": False,
            "reason": (
                f"credential '{name}' is not available; required by "
                f"credential/proxy route matching tool '{route['tool']}'"
            ),
        }

    def _append_annotation(
        self,
        session,
        route: dict[str, Any],
        index: int,
        used: list[str],
    ) -> None:
        session.log.append(
            type="annotation",
            payload={
                "kind": "credential_injected",
                "tool": route["tool"],
                "route_index": index,
                "credentials_used": used,
            },
        )

    def _append_runtime_error(self, session, reason: str, message: str) -> None:
        session.log.append(
            type="runtime_error",
            payload={
                "source": "strategy",
                "handler": "credential/proxy",
                "error_class": "Harnas::CredentialProxyError",
                "message": message,
                "reason": reason,
                "terminal": True,
            },
        )

    def _string_dict(self, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            raise ValueError("credential/proxy headers argument must be an object")
        return {str(key): str(item) for key, item in value.items()}
