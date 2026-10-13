# Python clients for HNAP devices

<!-- Code and releases -->
[![GitHub Release](https://img.shields.io/github/v/release/ldotlopez/ha-hnap-device?include_prereleases)](https://github.com/ldotlopez/python-hnap/releases)

[![Upload Python Package](https://github.com/ldotlopez/python-hnap/actions/workflows/python-publish.yml/badge.svg)](https://github.com/ldotlopez/python-hnap/actions/workflows/python-publish.yml)
[![CodeQL](https://github.com/ldotlopez/python-hnap/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/ldotlopez/python-hnap/actions/workflows/codeql-analysis.yml)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)

<!-- Sponsors -->
<a href="https://www.buymeacoffee.com/zepolson" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 30px !important;width: 105px !important;" ></a>

Generic HNAP client and specialized clients for  motion sensorts, sirens,
routers, water detectors and more.

## Creating and reconnecting devices

Pass a `DeviceType` to construct a known device without querying it first.
Pass `None` (or omit the type) to discover the device through HNAP:

```python
from hnap import DeviceConfig, DeviceFactory, DeviceType

config = DeviceConfig(hostname="192.0.2.10", password="secret")

# No discovery request is made during construction.
device = DeviceFactory(DeviceType.SIREN, config=config)

# Autodiscovery makes a request to determine the concrete device class.
discovered_device = DeviceFactory(None, config=config)
```

`DeviceConfig` is the single way to provide connection settings and retains
them independently of the client's authentication state. After a connection
is lost, call `device.reconnect()` on the existing instance. It authenticates
a fresh SOAP client before replacing the current one, preserves the device
class and module ID, and does not repeat type discovery. A failed reconnect
leaves the current client in place. Operations are not automatically retried
after transport errors because the device may have completed an action even
if its response was lost.

**Useful links**

  * [Product page](https://eu.dlink.com/es/es/products/dch-s220-mydlink-home-siren)
  * [REST API in NodeJS](https://github.com/mtflud/DCH-S220-Web-Control)
  * https://github.com/waffelheld/dlink-device-tracker
  * https://github.com/bikerp/dsp-w215-hnap
  * https://github.com/postlund/dlink_hnap
  * API for smart plugs: https://github.com/bikerp/dsp-w215-hnap/blob/master/js/soapclient.js
