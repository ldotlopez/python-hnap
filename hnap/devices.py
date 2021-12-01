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


import datetime
import enum
import logging

from .soapclient import MethodCallError, SoapClient

_LOGGER = logging.getLogger(__name__)


class Sound(enum.Enum):
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
            pass

        self._info = info

    @property
    def info(self):
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
    pass


class Motion(Device):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._delta = None

    @property
    def delta(self):
        return self._delta

    @delta.setter
    def delta(self, seconds):
        self.client.call(
            "SetMotionDetectorSettings", ModuleID=1, Backoff=self._delta
        )
        _LOGGER.warning("set delta property has no effect")

    def authenticate(self):
        super().authenticate()

        res = self.client.call("GetMotionDetectorSettings", ModuleID=1)
        try:
            self._delta = int(res["Backoff"])
        except (ValueError, TypeError, KeyError):
            _LOGGER.warning("Unable to get delta from device")

    def get_latest_detection(self):
        res = self.client.call("GetLatestDetection", ModuleID=1)
        return datetime.datetime.fromtimestamp(float(res["LatestDetectTime"]))

    def is_active(self):
        now = datetime.datetime.now()
        delta = (now - self.get_latest_detection()).total_seconds()

        return delta <= self.delta


class Router(Device):
    # NOT tested
    # See https://github.com/waffelheld/dlink-device-tracker/blob/master/custom_components/dlink_device_tracker/dlink_hnap.py#L95

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
    def is_playing(self):
        res = self.client.call(
            "GetSirenAlarmSettings", ModuleID=1, Controller=1
        )
        return res["IsSounding"] == "true"

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

    def beep(self, volume=100, duration=1):
        return self.client.play(
            sound=Sound.BEEP, duration=duration, volume=volume
        )

    def stop(self):
        ret = self.client.call("SetAlarmDismissed", ModuleID=1, Controller=1)

        if ret["SetAlarmDismissedResult"] != "OK":
            raise MethodCallError(f"Unable to stop. Response: {ret}")


class Water(Device):
    def is_active(self):
        ret = self.call("GetWaterDetectorState", ModuleID=1)
        return ret.get("IsWater") == "true"
