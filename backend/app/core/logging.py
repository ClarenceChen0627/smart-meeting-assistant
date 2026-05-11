from __future__ import annotations

import contextvars
import logging
from collections.abc import Iterator
from contextlib import contextmanager


_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
_meeting_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("meeting_id", default="-")
_job_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("job_id", default="-")
_provider_var: contextvars.ContextVar[str] = contextvars.ContextVar("provider", default="-")


class CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(record, "request_id", _request_id_var.get())
        record.meeting_id = getattr(record, "meeting_id", _meeting_id_var.get())
        record.job_id = getattr(record, "job_id", _job_id_var.get())
        record.provider = getattr(record, "provider", _provider_var.get())
        return True


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=(
            "%(asctime)s %(levelname)s [%(name)s] "
            "request_id=%(request_id)s meeting_id=%(meeting_id)s "
            "job_id=%(job_id)s provider=%(provider)s %(message)s"
        ),
    )
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if not any(isinstance(filter_, CorrelationFilter) for filter_ in handler.filters):
            handler.addFilter(CorrelationFilter())


def set_request_id(request_id: str) -> contextvars.Token[str]:
    return _request_id_var.set(request_id or "-")


def reset_request_id(token: contextvars.Token[str]) -> None:
    _request_id_var.reset(token)


@contextmanager
def correlation_context(
    *,
    meeting_id: str | None = None,
    job_id: str | None = None,
    provider: str | None = None,
) -> Iterator[None]:
    tokens: list[tuple[contextvars.ContextVar[str], contextvars.Token[str]]] = []
    if meeting_id is not None:
        tokens.append((_meeting_id_var, _meeting_id_var.set(meeting_id or "-")))
    if job_id is not None:
        tokens.append((_job_id_var, _job_id_var.set(job_id or "-")))
    if provider is not None:
        tokens.append((_provider_var, _provider_var.set(provider or "-")))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)
