# -*- coding: utf-8 -*-
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
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.


import functools
import hashlib
import hmac
import logging
import time
import xml.dom.minidom

import requests
import xmltodict

_LOGGER = logging.getLogger(__name__)


def hex_hmac_md5(a: str, b: str) -> str:
    return hmac.new(a.encode("ascii"), b.encode("ascii"), hashlib.md5).hexdigest()


def auth_required(fn):
    @functools.wraps(fn)
    def _wrap(soapclient, *args, **kwargs):
        if not soapclient.authenticated:
            soapclient.authenticate()
            _LOGGER.debug("SoapClient authenticated")
        return fn(soapclient, *args, **kwargs)

    return _wrap


class SoapClient:
    HNAP1_XMLNS = "http://purenetworks.com/HNAP1/"
    HNAP_METHOD = "POST"
    HNAP_BODY_ENCODING = "UTF8"
    HNAP_LOGIN_METHOD = "Login"
    HNAP_AUTH = {
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
        hostname,
        password,
        username="admin",
        port=80,
        request_timeout=10,
        session_lifetime=3600,
    ):
        self._hostname = hostname
        self._port = port
        self._request_timeout = request_timeout
        self._session_lifetime = session_lifetime

        self.HNAP_AUTH = self.HNAP_AUTH.copy()
        self.HNAP_AUTH["url"] = self.HNAP_AUTH["url"].format(
            hostname=hostname, port=port
        )
        self.HNAP_AUTH["username"] = username
        self.HNAP_AUTH["password"] = password
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

    @property
    def authenticated(self):
        return (self._authenticated > 0) and (
            (time.monotonic() - self._authenticated) <= self._session_lifetime
        )

    def _build_method_envelope(self, method, **parameters):
        parameters_xml = "\n".join(
            [f"     <{k}>{v}</{k}>" for (k, v) in parameters.items()]
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

        for (tag, key) in [
            ("Challenge", "challenge"),
            ("PublicKey", "public_key"),
            ("Cookie", "cookie"),
        ]:
            elements = doc.getElementsByTagName(tag)
            self.HNAP_AUTH[key] = elements[0].firstChild.nodeValue

        self.HNAP_AUTH["private_key"] = hex_hmac_md5(
            self.HNAP_AUTH["public_key"] + self.HNAP_AUTH["password"],
            self.HNAP_AUTH["challenge"],
        ).upper()

    def _getHNAP_auth(self, soap_action, private_key):
        time_stamp = int(time.mktime(time.localtime()))
        auth = hex_hmac_md5(private_key, str(time_stamp) + soap_action)
        ret = auth.upper() + " " + str(time_stamp)

        return ret

    def call_raw(self, method, **parameters):
        req_url = self.HNAP_AUTH["url"]
        req_method = self.HNAP_METHOD
        req_headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f'"{self.HNAP1_XMLNS}{method}"',
            "HNAP_AUTH": self._getHNAP_auth(
                f'"{self.HNAP1_XMLNS}{method}"',
                self.HNAP_AUTH["private_key"],
            ),
            "Cookie": "uid=" + self.HNAP_AUTH["cookie"],
        }

        resp = requests.request(
            method=req_method,
            url=req_url,
            headers=req_headers,
            data=self._build_method_envelope(method, **parameters),
            timeout=self._request_timeout,
        )

        if resp.status_code != 200:
            raise MethodCallError(
                f"Invalid status code: {resp.status_code}", resp.status_code
            )
        return resp.text

    def call(self, method, **parameters):
        parsed = xmltodict.parse(self.call_raw(method, **parameters))
        try:
            res = parsed["soap:Envelope"]["soap:Body"][f"{method}Response"][
                f"{method}Result"
            ]
            if res.lower() not in ("ok", "success"):
                raise MethodCallError(f"{method} returned {res}")

        except KeyError:
            raise MethodCallError(f"Missing {method}Result key")

        return parsed["soap:Envelope"]["soap:Body"][f"{method}Response"]

    def authenticate(self, force=False):
        if self.authenticated and not force:
            _LOGGER.debug("Client already authenticated")
            return

        url = self.HNAP_AUTH["url"]
        method = self.HNAP_METHOD
        data = self._build_method_envelope(
            self.HNAP_LOGIN_METHOD,
            Action="request",
            Username=self.HNAP_AUTH["username"],
            LoginPassword="",
            Captcha="",
        )
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": '"' + self.HNAP1_XMLNS + self.HNAP_LOGIN_METHOD + '"',
        }

        resp = requests.request(
            method=method,
            url=url,
            data=data,
            headers=headers,
            timeout=self._request_timeout,
        )

        if resp.status_code != 200:
            raise AuthenticationError(
                f"Invalid response while login: {resp.status_code} ({resp.text})"
            )

        self._save_login_result(resp.text)

        # Phase 2
        login_password = hex_hmac_md5(
            self.HNAP_AUTH["private_key"], self.HNAP_AUTH["challenge"]
        ).upper()

        res = self.call(
            self.HNAP_LOGIN_METHOD,
            Action="login",
            Username=self.HNAP_AUTH["username"],
            LoginPassword=login_password,
            Captcha="",
        )

        if res["LoginResult"] != "success":
            raise AuthenticationError(res["LoginResult"])

        self._authenticated = time.monotonic()

    @auth_required
    def soap_actions(self):
        resp = self.call("GetModuleSOAPActions", ModuleID=1)
        actions = resp["ModuleSOAPList"]["SOAPActions"]["Action"]

        return actions

    @auth_required
    def device_info(self):
        info = dict(self.call("GetDeviceSettings"))
        for k in ["@xmlns", "SOAPActions", "GetDeviceSettingsResult"]:
            info.pop(k, None)

        try:
            info["ModuleTypes"] = info["ModuleTypes"]["string"]
        except KeyError:
            pass

        return info

    @auth_required
    def device_actions(self):
        idx = len(self.HNAP1_XMLNS)

        resp = self.call("GetDeviceSettings")
        actions = resp["SOAPActions"]["string"]
        actions = (x for x in actions if x.startswith(self.HNAP1_XMLNS))
        actions = (x[idx:] for x in actions)

        return list(actions)


class ClientError(Exception):
    pass


class AuthenticationError(ClientError):
    pass


class MethodCallError(ClientError):
    pass
