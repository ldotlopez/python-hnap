#
# Copyright (C) 2021 Luis López <luis@cuarentaydos.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

import hashlib
import hmac
import logging
import time
import xml.dom.minidom
from typing import ClassVar

import aiohttp
import xmltodict

from .config import DeviceConfig
from .const import DEFAULT_MODULE_ID
from .helpers import auth_required

_LOGGER = logging.getLogger(__name__)


def hex_hmac_md5(a: str, b: str) -> str:
    return hmac.new(a.encode("ascii"), b.encode("ascii"), hashlib.md5).hexdigest()


class SoapClient:
    HNAP1_XMLNS = "http://purenetworks.com/HNAP1/"
    HNAP_METHOD = "POST"
    HNAP_BODY_ENCODING = "UTF8"
    HNAP_LOGIN_METHOD = "Login"
    HNAP_AUTH: ClassVar[dict[str, str | None]] = {
        "challenge": "",
        "cookie": "",
        "private_key": "",
        "public_key": "",
        "password": None,
        "result": "",
        "url": "http://{hostname}:{port}/HNAP1/",
        "username": None,
    }

    def __init__(
        self,
        config: DeviceConfig,
        *,
        http_client: aiohttp.ClientSession | None = None,
    ):
        if not isinstance(config, DeviceConfig):
            raise TypeError("config must be a DeviceConfig")
        self.http_client = http_client
        self._owns_http_client = http_client is None
        self.config = config
        self._hostname = config.hostname
        self._port = config.port
        self._request_timeout = config.request_timeout
        self._session_lifetime = config.session_lifetime
        self.HNAP_AUTH = self.HNAP_AUTH.copy()
        self.HNAP_AUTH["url"] = self.HNAP_AUTH["url"].format(
            hostname=config.hostname, port=config.port
        )
        self.HNAP_AUTH["username"] = config.username
        self.HNAP_AUTH["password"] = config.password
        self._authenticated = 0

    @property
    def hostname(self):
        return self._hostname

    @property
    def port(self):
        return self._port

    @property
    def username(self):
        return self.HNAP_AUTH["username"]

    @property
    def password(self):
        return self.HNAP_AUTH["password"]

    async def start(self) -> aiohttp.ClientSession:
        if self.http_client is None:
            self.http_client = aiohttp.ClientSession()
        return self.http_client

    def _build_method_envelope(self, method, **parameters):
        parameters_xml = "\n".join(
            [f"     <{key}>{value}</{key}>" for key, value in parameters.items()]
        )
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            "<soap:Envelope "
            '  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            '  xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
            '  xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            "  <soap:Body>"
            f'   <{method} xmlns="{self.HNAP1_XMLNS}">'
            f"     {parameters_xml}"
            f"   </{method}>"
            "  </soap:Body>"
            "</soap:Envelope>"
        )

    def _save_login_result(self, body):
        doc = xml.dom.minidom.parseString(body)
        self.HNAP_AUTH["result"] = doc.getElementsByTagName(
            f"{self.HNAP_LOGIN_METHOD}Result"
        )[0].firstChild.nodeValue
        for tag, key in (
            ("Challenge", "challenge"),
            ("PublicKey", "public_key"),
            ("Cookie", "cookie"),
        ):
            elements = doc.getElementsByTagName(tag)
            self.HNAP_AUTH[key] = elements[0].firstChild.nodeValue
        self.HNAP_AUTH["private_key"] = hex_hmac_md5(
            self.HNAP_AUTH["public_key"] + self.HNAP_AUTH["password"],
            self.HNAP_AUTH["challenge"],
        ).upper()

    def _get_hnap_auth(self, soap_action, private_key):
        timestamp = int(time.time())
        auth = hex_hmac_md5(private_key, str(timestamp) + soap_action)
        return f"{auth.upper()} {timestamp}"

    async def call_raw(self, method, **parameters):
        http_client = await self.start()
        soap_action = f'"{self.HNAP1_XMLNS}{method}"'
        async with http_client.request(
            self.HNAP_METHOD,
            self.HNAP_AUTH["url"],
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": soap_action,
                "HNAP_AUTH": self._get_hnap_auth(
                    soap_action, self.HNAP_AUTH["private_key"]
                ),
                "Cookie": f"uid={self.HNAP_AUTH['cookie']}",
            },
            data=self._build_method_envelope(method, **parameters),
            timeout=self._request_timeout,
        ) as response:
            response_text = await response.text()
        if response.status != 200:
            raise MethodCallError(
                f"Invalid status code: {response.status}", response.status
            )
        return response_text

    async def call(self, method, **parameters):
        parsed = xmltodict.parse(await self.call_raw(method, **parameters))
        try:
            result = parsed["soap:Envelope"]["soap:Body"][f"{method}Response"][
                f"{method}Result"
            ]
            if result.lower() not in ("ok", "success"):
                raise MethodCallError(f"{method} returned {result}")
        except KeyError:
            raise MethodCallError(f"Missing {method}Result key") from None
        return parsed["soap:Envelope"]["soap:Body"][f"{method}Response"]

    async def authenticate(self, force=False):
        if await self.is_authenticated() and not force:
            _LOGGER.debug("Client already authenticated")
            return

        http_client = await self.start()
        async with http_client.request(
            self.HNAP_METHOD,
            self.HNAP_AUTH["url"],
            data=self._build_method_envelope(
                self.HNAP_LOGIN_METHOD,
                Action="request",
                Username=self.HNAP_AUTH["username"],
                LoginPassword="",
                Captcha="",
            ),
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": f'"{self.HNAP1_XMLNS}{self.HNAP_LOGIN_METHOD}"',
            },
            timeout=self._request_timeout,
        ) as response:
            response_text = await response.text()
        if response.status != 200:
            raise AuthenticationError(
                f"Invalid response while login: {response.status} ({response_text})"
            )

        self._save_login_result(response_text)
        login_password = hex_hmac_md5(
            self.HNAP_AUTH["private_key"], self.HNAP_AUTH["challenge"]
        ).upper()
        result = await self.call(
            self.HNAP_LOGIN_METHOD,
            Action="login",
            Username=self.HNAP_AUTH["username"],
            LoginPassword=login_password,
            Captcha="",
        )
        if result["LoginResult"] != "success":
            raise AuthenticationError(result["LoginResult"])
        self._authenticated = time.monotonic()

    async def is_authenticated(self):
        return self._authenticated > 0 and (
            time.monotonic() - self._authenticated <= self._session_lifetime
        )

    async def close(self):
        if self._owns_http_client and self.http_client is not None:
            await self.http_client.close()
            self.http_client = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.close()

    async def _inspect_device(self, **kwargs):
        def unwrap_string_ordered_dict(data):
            values = []
            for value_type, value in data.items():
                if value_type != "string":
                    _LOGGER.warning("Unknown type class: (%s, %s)", value_type, value)
                    continue
                if isinstance(value, str):
                    values.append(value)
                elif isinstance(value, list):
                    values.extend(value)
                else:
                    _LOGGER.error("Unknown value instance: (%r)", value)
            return values

        info = dict(await self.call("GetDeviceSettings", **kwargs))
        info["ModuleTypes"] = (
            unwrap_string_ordered_dict(info["ModuleTypes"])
            if "ModuleTypes" in info
            else []
        )
        info["SOAPActions"] = unwrap_string_ordered_dict(info["SOAPActions"])
        return info

    @auth_required
    async def device_info(self, **kwargs):
        info = await self._inspect_device(**kwargs)
        for key in ("@xmlns", "SOAPActions", "GetDeviceSettingsResult"):
            info.pop(key, None)
        return info

    @auth_required
    async def device_actions(self, **kwargs):
        info = await self._inspect_device(**kwargs)
        return [
            action[len(self.HNAP1_XMLNS) :]
            for action in info["SOAPActions"]
            if action.startswith(self.HNAP1_XMLNS)
        ]

    @auth_required
    async def module_actions(self, *, ModuleID=DEFAULT_MODULE_ID, **kwargs):
        response = await self.call("GetModuleSOAPActions", ModuleID=ModuleID, **kwargs)
        return response["ModuleSOAPList"]["SOAPActions"]["Action"]


class ClientError(Exception):
    pass


class AuthenticationError(ClientError):
    pass


class MethodCallError(ClientError):
    pass
