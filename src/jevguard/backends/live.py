"""Live Jev backend using the official `typesafe-sdk` (optional extra: jevguard[live])."""
from __future__ import annotations

import time
from typing import Any

from jevguard.backends.base import BackendError
from jevguard.schemas import JevResponse, parse_response


class LiveBackend:
    name = "live"

    def __init__(
        self,
        model: str = "jev-latest",
        *,
        timeout: float = 5.0,
        max_retries: int = 1,
        endpoint: str = "typesafe",
        client: Any = None,
        **client_kwargs: Any,
    ):
        self.endpoint = endpoint
        if client is None:
            try:
                from typesafe_sdk import RetryPolicy, TypeSafeClient
            except ImportError as exc:  # pragma: no cover - exercised only without the extra
                raise ImportError("install the live extra: pip install 'jevguard[live]'") from exc
            client = TypeSafeClient(
                model=model,
                retry=RetryPolicy(max_retries=max_retries, timeout=timeout),
                **client_kwargs,
            )
        self._client = client

    def ask(self, state: Any, questions: dict[str, dict[str, Any]]) -> JevResponse:
        t0 = time.perf_counter()
        try:
            result = self._client.system_one(state, questions)
            raw = result.raw_http_response.json()
            request_id = getattr(result, "request_id", None)
            latency_ms = (time.perf_counter() - t0) * 1000
            return parse_response(raw, request_id=request_id, latency_ms=latency_ms, endpoint=self.endpoint)
        except Exception as exc:  # safety layer: any failure must fail closed, never crash the caller
            raise BackendError(f"{type(exc).__name__}: {exc}") from exc
