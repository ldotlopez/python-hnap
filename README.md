# Python clients for HNAP devices

<!-- Code and releases -->
[![GitHub Release](https://img.shields.io/github/v/release/ldotlopez/ha-hnap-device?include_prereleases)](https://github.com/ldotlopez/python-hnap/releases)

[![Upload Python Package](https://github.com/ldotlopez/python-hnap/actions/workflows/python-publish.yml/badge.svg)](https://github.com/ldotlopez/python-hnap/actions/workflows/python-publish.yml)
[![CodeQL](https://github.com/ldotlopez/python-hnap/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/ldotlopez/python-hnap/actions/workflows/codeql-analysis.yml)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)

<!-- Sponsors -->
<a href="https://www.buymeacoffee.com/zepolson" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 30px !important;width: 105px !important;" ></a>

Generic HNAP client and specialized clients for motion sensors, sirens,
routers, water detectors and more.

## Async devices

All network operations are asynchronous. Pass a `DeviceType` to construct a
known device without querying it first, or omit the type to discover the
concrete device:

```python
import asyncio

import aiohttp
from hnap import DeviceConfig, DeviceFactory, DeviceType

config = DeviceConfig(hostname="192.0.2.10", password="secret")


async def main():
    async with aiohttp.ClientSession() as http_client:
        siren = await DeviceFactory(
            DeviceType.SIREN, config=config, http_client=http_client
        )
        await siren.authenticate()
        await siren.soap_client.call("GetSirenAlarmSettings")

        discovered = await DeviceFactory(config=config)
        async with discovered:
            await discovered.authenticate()


asyncio.run(main())
```

`DeviceConfig` retains connection settings independently of authentication
state. Operations are not retried after transport errors because the device
may have completed an action even if its response was lost.

`SoapClient` creates an `aiohttp.ClientSession` when `await client.start()` is
called, when the client or device is entered as an async context manager, or
before its first network request. Sessions created by HNAP are closed by
`await client.close()` or on context-manager exit. You can instead supply an
existing session via `http_client`; caller-supplied sessions remain
caller-owned and are not closed by the SOAP client or device.

Device operations such as `is_playing()`, `play()`, `beep()`, and
`get_clients()` must be awaited. Cached device information is retrieved with
`await device.get_info()`.

## Command-line interface

The `hnap` command requires a hostname and password (or `HNAP_PASSWORD`) and
provides three subcommands:

```console
hnap --hostname 192.0.2.10 --password secret inspect
hnap --hostname 192.0.2.10 --password secret monitor --seconds 10
hnap --hostname 192.0.2.10 --password secret call GetDeviceSettings --param Module 1
```

`inspect` reports the device's module types and settings. `monitor` calls
`IsDeviceReady` immediately and repeats every 30 seconds by default; use
`--seconds` to change the interval. `call` invokes a raw SOAP action and accepts
repeated `--param NAME VALUE` arguments.

**Useful links**

  * [Product page](https://eu.dlink.com/es/es/products/dch-s220-mydlink-home-siren)
  * [REST API in NodeJS](https://github.com/mtflud/DCH-S220-Web-Control)
  * https://github.com/waffelheld/dlink-device-tracker
  * https://github.com/bikerp/dsp-w215-hnap
  * https://github.com/postlund/dlink_hnap
  * API for smart plugs: https://github.com/bikerp/dsp-w215-hnap/blob/master/js/soapclient.js
