# Repository guidance

## Build, checks, and tests

- Build the distributable with `python -m build` (the `build` package is listed as a development dependency in `Pipfile`).
- Run the configured formatting and lint hooks with `pre-commit run --all-files`. The hooks include Black, isort, pyupgrade, and common file-format checks.
- Run tests with `python -m unittest discover -s tests`; run one test file with `python -m unittest discover -s tests -p 'test_device_factory.py'`.
- The package requires Python 3.11 or newer, as specified in `pyproject.toml`.
- Do not run tests or builds unless the user asks. Ask the user before preparing a new release.

## Scope of requests

- “Evaluate” and “plan” requests are for analysis or proposals, not code changes. Only edit code when the user explicitly asks for implementation.

## Architecture

- `hnap/soapclient.py` is the protocol layer. `SoapClient` builds HNAP SOAP XML requests, sends them over HTTP with `aiohttp`, parses XML responses with `xmltodict`, performs the two-stage HNAP login, and discovers device information and available actions.
- `hnap/devices.py` builds the higher-level device API on top of `SoapClient`. `Device` delegates calls to the client and adds the module ID; specialized classes expose operations for cameras, motion sensors, routers, sirens, and water detectors. `DeviceFactory(DeviceType, ...)` constructs a known class without discovery; `DeviceFactory(None, ...)` currently discovers Audio Renderer, Camera, and Motion Sensor devices over HNAP.
- `hnap/config.py` defines immutable `DeviceConfig` connection settings. It is the single connection-settings input to device construction and `SoapClient`. `Device.reconnect()` authenticates a new client before swapping it into the existing device; it reuses the resolved type and module ID without rediscovery.
- `hnap/helpers.py` contains the `auth_required` decorator used by protected device and client operations to authenticate an expired or unauthenticated session before proceeding.
- `hnap/cli.py` is the command-line entry point: it can display device/action information or invoke a raw SOAP action. `hnap/__main__.py` enables `python -m hnap`; the installed `hnap` command is declared in `pyproject.toml`.
- `hnap/const.py` centralizes default module ID, port, timeout, session lifetime, and username. The package exports its public client, device classes, and exceptions from `hnap/__init__.py`.

## Conventions specific to this project

- Keep protocol concerns in `SoapClient` and device-specific behavior in `Device` subclasses; use the shared `call` path rather than duplicating HTTP/SOAP handling in a device class.
- Use `auth_required` for operations that require an authenticated device session. `SoapClient` tracks authentication lifetime and owns the login exchange.
- Prefer an explicit `DeviceType` when known to avoid a discovery request. Use `None` only when device-type discovery is intended. After transport loss, call `device.reconnect()` to restore the existing object; device actions are not automatically retried because their completion may be ambiguous.
- Device SOAP operations use HNAP action names and response keys as provided by the device. When changing these, preserve the expected response/result handling and verify against device behavior where possible.
- Use the existing Black formatting and isort's Black profile; the pre-commit configuration is the source of truth for these checks.
