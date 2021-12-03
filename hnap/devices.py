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
import logging
from datetime import datetime
from enum import Enum

from .soapclient import MethodCallError, SoapClient

_LOGGER = logging.getLogger(__name__)


def auth_required(fn):
    @functools.wraps(fn)
    def _wrap(self, *args, **kwargs):
        if not self.authenticated:
            self.authenticate()
        return fn(self, *args, **kwargs)

    return _wrap


class Sound(Enum):
    EMERGENCY = 1
    FIRE = 2
    AMBULANCE = 3
    POLICE = 4
    DOOR_CHIME = 5
    BEEP = 6

    @classmethod
    def fromstring(cls, s):
        s = s.upper()
        for c in ["-", " ", "."]:
            s = s.replace(c, "_")

        return getattr(cls, s)


class Device:
    REQUIRED_MODULE_TYPES: list[str] = []

    def __init__(
        self,
        *,
        client=None,
        hostname=None,
        password=None,
        username="Admin",
        port=80,
    ):
        self.client = client or SoapClient(
            hostname=hostname, password=password, username=username, port=port
        )
        self._info = None

    def authenticate(self):
        self.client.authenticate()

        info = dict(self.client.call("GetDeviceSettings"))
        for k in ["@xmlns", "SOAPActions", "GetDeviceSettingsResult"]:
            info.pop(k, None)

        try:
            info["ModuleTypes"] = info["ModuleTypes"]["string"]
        except KeyError:
            info["ModuleTypes"] = []

        if isinstance(info["ModuleTypes"], str):
            info["ModuleTypes"] = [info["ModuleTypes"]]

        dev = set(info["ModuleTypes"])
        req = set(self.REQUIRED_MODULE_TYPES)
        if not req.issubset(dev):
            raise TypeError(
                f"device '{self.client.hostname}' is not a "
                f"{self.__class__.__name__}",
            )

        self._info = info

    @property
    def authenticated(self):
        return self._info is not None

    @property
    def info(self):
        if not self.authenticated:
            self.authenticate()
        return self._info


def DeviceFactory(
    *, client=None, hostname=None, password=None, username="Admin", port=80
):
    client = client or SoapClient(
        hostname=hostname, password=password, username=username, port=port
    )
    client.authenticate()
    info = client.device_info()

    module_types = info["ModuleTypes"]
    if not isinstance(module_types, list):
        module_types = [module_types]

    if "Audio Renderer" in module_types:
        cls = Siren
    # 'Optical Recognition', 'Environmental Sensor', 'Camera']
    elif "Camera" in module_types:
        cls = Camera
    elif "Motion Sensor" in module_types:
        cls = Motion
    else:
        raise TypeError(module_types)

    return cls(client=client)


class Camera(Device):
    REQUIRED_MODULE_TYPES = ["Camera"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._base_url = (
            "http://"
            + f"{self.client.username.lower()}:{self.client.password}@"
            + f"{self.client.hostname}:{self.client.port}"
        )

    @property
    def stream_url(self):
        return f"{self._base_url}/play1.sdp"

    @property
    def picture_url(self):
        return f"{self._base_url}/image/jpeg.cgi"


class Motion(Device):
    REQUIRED_MODULE_TYPES = ["Motion Sensor"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._backoff = None

    @property
    def backoff(self):
        return self._backoff

    # @backoff.setter
    # def backoff(self, seconds):
    #     self.client.call(
    #         "SetMotionDetectorSettings", ModuleID=1, Backoff=self._backoff
    #     )
    #     _LOGGER.warning("set backoff property has no effect")

    def authenticate(self):
        super().authenticate()

        res = self.client.call("GetMotionDetectorSettings", ModuleID=1)
        try:
            self._backoff = int(res["Backoff"])
        except (ValueError, TypeError, KeyError):
            _LOGGER.warning("Unable to get delta from device")

    @auth_required
    def get_latest_detection(self):
        res = self.client.call("GetLatestDetection", ModuleID=1)
        return datetime.datetime.fromtimestamp(float(res["LatestDetectTime"]))

    @auth_required
    def is_active(self):
        now = datetime.datetime.now()
        diff = (now - self.get_latest_detection()).total_seconds()

        return diff <= self._backoff


class Router(Device):
    # NOT tested
    # See https://github.com/waffelheld/dlink-device-tracker/blob/master/custom_components/dlink_device_tracker/dlink_hnap.py#L95
    REQUIRED_MODULE_TYPES = ["check-module-types-for-router"]

    @auth_required
    def get_clients(self):
        res = self.call("GetClientInfo", ModuleID=1, Controller=1)
        clients = res["ClientInfoLists"]["ClientInfo"]

        # Filter out offline clients
        # clients = [x for x in clients if x["Type"] != "OFFLINE"]

        ret = [
            {
                "name": client["DeviceName"],
                "nickName": client["NickName"],
                "is_connected": client["Type"] == "OFFLINE" and 0 or 1,
                "mac": client["MacAddress"],
            }
            for client in clients
        ]
        return ret


class Siren(Device):
    REQUIRED_MODULE_TYPES = ["Audio Renderer"]

    @auth_required
    def is_playing(self):
        res = self.client.call(
            "GetSirenAlarmSettings", ModuleID=1, Controller=1
        )
        return res["IsSounding"] == "true"

    @auth_required
    def play(self, sound=Sound.EMERGENCY, volume=100, duration=60):
        ret = self.client.call(
            "SetSoundPlay",
            ModuleID=1,
            Controller=1,
            SoundType=sound.value,
            Volume=volume,
            Duration=duration,
        )
        if ret["SetSoundPlayResult"] != "OK":
            raise MethodCallError(f"Unable to play. Response: {ret}")

    @auth_required
    def beep(self, volume=100, duration=1):
        return self.client.play(
            sound=Sound.BEEP, duration=duration, volume=volume
        )

    @auth_required
    def stop(self):
        ret = self.client.call("SetAlarmDismissed", ModuleID=1, Controller=1)

        if ret["SetAlarmDismissedResult"] != "OK":
            raise MethodCallError(f"Unable to stop. Response: {ret}")


class Water(Device):
    # NOT tested
    REQUIRED_MODULE_TYPES = ["check-module-types-for-water-detector"]

    @auth_required
    def is_active(self):
        ret = self.call("GetWaterDetectorState", ModuleID=1)
        return ret.get("IsWater") == "true"
