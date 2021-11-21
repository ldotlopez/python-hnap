#!/usr/bin/env python3

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
    _HNAP1_XMLNS = "http://purenetworks.com/HNAP1/"
    _HNAP_METHOD = "POST"
    _HNAP_BODY_ENCODING = "UTF8"
    _HNAP_LOGIN_METHOD = "Login"
    _HNAP_AUTH = {
        "challenge": "",
        "cookie": "",
        "private_key": "",
        "public_key": "",
        "pin": None,
        "result": "",
        "url": "http://{hostname}/HNAP1",
        "username": None,
    }

    def __init__(self, hostname, pin, username="admin"):
        self._HNAP_AUTH["url"] = self._HNAP_AUTH["url"].format(
            hostname=hostname
        )
        self._HNAP_AUTH["username"] = username
        self._HNAP_AUTH["pin"] = pin

    def _build_method_envelope(self, method, parameters):
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            "<soap:Envelope "
            '  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            '  xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
            '  xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            "  <soap:Body>"
            f'   <{method} xmlns="{self._HNAP1_XMLNS}">'
            f"     {parameters}"
            f"   </{method}>"
            "  </soap:Body>"
            "</soap:Envelope>"
        )

    def _save_login_result(self, body):
        doc = xml.dom.minidom.parseString(body)
        self._HNAP_AUTH["result"] = doc.getElementsByTagName(
            f"{self._HNAP_LOGIN_METHOD}Result"
        )[0].firstChild.nodeValue

        for (tag, key) in [
            ("Challenge", "challenge"),
            ("PublicKey", "public_key"),
            ("Cookie", "cookie"),
        ]:
            elements = doc.getElementsByTagName(tag)
            self._HNAP_AUTH[key] = elements[0].firstChild.nodeValue

        self._HNAP_AUTH["private_key"] = hex_hmac_md5(
            self._HNAP_AUTH["public_key"] + self._HNAP_AUTH["pin"],
            self._HNAP_AUTH["challenge"],
        ).upper()

    def _get_hnap_auth(self, soap_action, private_key):
        time_stamp = int(time.mktime(time.localtime()))
        auth = hex_hmac_md5(private_key, str(time_stamp) + soap_action)
        ret = auth.upper() + " " + str(time_stamp)

        return ret

    def _extract_response(self, body, element_name):
        doc = xml.dom.minidom.parseString(body)
        node = doc.getElementsByTagName(element_name)[0]
        if not node or not node.firstChild:
            raise Exception()

        return node.firstChild.nodeValue

    def execute_and_parse(self, method, response_element, body):
        req_url = self._HNAP_AUTH["url"]
        req_method = self._HNAP_METHOD
        req_headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f'"{self._HNAP1_XMLNS}{method}"',
            "HNAP_AUTH": self._get_hnap_auth(
                f'"{self._HNAP1_XMLNS}{method}"',
                self._HNAP_AUTH["private_key"],
            ),
            "Cookie": "uid=" + self._HNAP_AUTH["cookie"],
        }

        resp = requests.request(
            method=req_method, url=req_url, headers=req_headers, data=body
        )

        if resp.status_code != 200:
            raise Exception("Invalid status code", resp.status_code)

        return self._extract_response(resp.text, response_element)

    def login(self):
        # Phase 1
        request_params = (
            "<Action>request</Action>"
            "<Username>" + self._HNAP_AUTH["username"] + "</Username>"
            "<LoginPassword></LoginPassword>"
            "<Captcha></Captcha>"
        )

        url = self._HNAP_AUTH["url"]
        method = self._HNAP_METHOD
        data = self._build_method_envelope(
            self._HNAP_LOGIN_METHOD, request_params
        )
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": '"'
            + self._HNAP1_XMLNS
            + self._HNAP_LOGIN_METHOD
            + '"',
        }
        resp = requests.request(
            method=method, url=url, data=data, headers=headers
        )
        if resp.status_code != 200:
            raise Exception()
        self._save_login_result(resp.text)

        # Phase 2
        login_password = hex_hmac_md5(
            self._HNAP_AUTH["private_key"], self._HNAP_AUTH["challenge"]
        ).upper()

        login_params = (
            "<Action>login</Action>"
            "<Username>" + self._HNAP_AUTH["username"] + "</Username>"
            "<LoginPassword>" + login_password + "</LoginPassword>"
            "<Captcha></Captcha>"
        )

        res = self.execute_and_parse(
            self._HNAP_LOGIN_METHOD,
            "LoginResult",
            self._build_method_envelope(self._HNAP_LOGIN_METHOD, login_params),
        )

        if res != "success":
            raise Exception("Login failed")
