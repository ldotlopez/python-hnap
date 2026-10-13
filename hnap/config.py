from dataclasses import dataclass, field

from .const import (
    DEFAULT_PORT,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_SESSION_LIFETIME,
    DEFAULT_USERNAME,
)


@dataclass(frozen=True)
class DeviceConfig:
    hostname: str
    password: str = field(repr=False)
    username: str = DEFAULT_USERNAME
    port: int = DEFAULT_PORT
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT
    session_lifetime: float = DEFAULT_SESSION_LIFETIME

    def __post_init__(self):
        if not self.hostname:
            raise ValueError("hostname is required")
        if self.password is None:
            raise ValueError("password is required")
