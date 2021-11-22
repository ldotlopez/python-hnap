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


import hashlib
import hmac
import time
import xml.dom.minidom

import requests


def hex_hmac_md5(a: str, b: str) -> str:
    return hmac.new(
        a.encode("ascii"), b.encode("ascii"), hashlib.md5
    ).hexdigest()


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
        "pin": None,
        "result": "",
        "url": "http://{hostname}:{port}/HNAP1",
        "username": None,
    }

    def __init__(self, hostname, pin, username="admin", port=80):
        self.HNAP_AUTH = self.HNAP_AUTH.copy()
        self.HNAP_AUTH["url"] = self.HNAP_AUTH["url"].format(
            hostname=hostname, port=port
        )
        self.HNAP_AUTH["username"] = username
        self.HNAP_AUTH["pin"] = pin

    def _build_method_envelope(self, method, parameters):
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            "<soap:Envelope "
            '  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            '  xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
            '  xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            "  <soap:Body>"
            f'   <{method} xmlns="{self.HNAP1_XMLNS}">'
            f"     {parameters}"
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
            self.HNAP_AUTH["public_key"] + self.HNAP_AUTH["pin"],
            self.HNAP_AUTH["challenge"],
        ).upper()

    def _getHNAP_auth(self, soap_action, private_key):
        time_stamp = int(time.mktime(time.localtime()))
        auth = hex_hmac_md5(private_key, str(time_stamp) + soap_action)
        ret = auth.upper() + " " + str(time_stamp)

        return ret

    def _extract_response(self, body, element_name):
        doc = xml.dom.minidom.parseString(body)
        node = doc.getElementsByTagName(element_name)[0]
        if not node or not node.firstChild:
            raise MethodCallError(
                f"Invalid response, unable to find {element_name} element in "
                f"{body}",
                body,
            )

        return node.firstChild.nodeValue

    def execute_and_parse(self, method, response_element, body):
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
            method=req_method, url=req_url, headers=req_headers, data=body
        )

        if resp.status_code != 200:
            raise MethodCallError(
                f"Invalid status code: {resp.status_code}", resp.status_code
            )

        return self._extract_response(resp.text, response_element)

    def login(self):
        # Phase 1
        request_params = (
            "<Action>request</Action>"
            "<Username>" + self.HNAP_AUTH["username"] + "</Username>"
            "<LoginPassword></LoginPassword>"
            "<Captcha></Captcha>"
        )

        url = self.HNAP_AUTH["url"]
        method = self.HNAP_METHOD
        data = self._build_method_envelope(
            self.HNAP_LOGIN_METHOD, request_params
        )
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": '"'
            + self.HNAP1_XMLNS
            + self.HNAP_LOGIN_METHOD
            + '"',
        }
        resp = requests.request(
            method=method, url=url, data=data, headers=headers
        )
        if resp.status_code != 200:
            raise MethodCallError(resp.status_code, resp.text)

        self._save_login_result(resp.text)

        # Phase 2
        login_password = hex_hmac_md5(
            self.HNAP_AUTH["private_key"], self.HNAP_AUTH["challenge"]
        ).upper()

        login_params = (
            "<Action>login</Action>"
            "<Username>" + self.HNAP_AUTH["username"] + "</Username>"
            "<LoginPassword>" + login_password + "</LoginPassword>"
            "<Captcha></Captcha>"
        )

        res = self.execute_and_parse(
            self.HNAP_LOGIN_METHOD,
            "LoginResult",
            self._build_method_envelope(self.HNAP_LOGIN_METHOD, login_params),
        )

        if res != "success":
            raise AuthenticationError()


class ClientError(Exception):
    pass


class AuthenticationError(ClientError):
    pass


class MethodCallError(ClientError):
    pass
