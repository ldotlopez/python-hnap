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

from .soapclient import MethodCallError, SoapClient


def DeviceFactory(hostname, password, username="Admin", port=80, **kwargs):
    device = SoapClient(hostname, password, username, port)
    device.authenticate()
    info = device.device_info()

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

    return cls(hostname, password, username=username, port=port, **kwargs)


class _Device(SoapClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._info = None

    def authenticate(self):
        super().authenticate()
        self._info = self.device_info()

    @property
    def info(self):
        return self._info


class Camera(_Device):
    pass


class Motion(_Device):
    def __init__(self, *args, delta=30, **kwargs):
        super().__init__(*args, **kwargs)
        self.delta = delta

    def login(self):
        super().login()

        # Auto-adjust delta
        res = self.call(
            "SetMotionDetectorSettings", ModuleID=1, Backoff=self.delta
        )
        res = self.call("GetMotionDetectorSettings", ModuleID=1)
        try:
            self.delta = int(res["Backoff"])
        except (ValueError, TypeError):
            self.delta = 30

    def get_latest_detection(self):
        res = self.call("GetLatestDetection", ModuleID=1)
        return datetime.datetime.fromtimestamp(float(res["LatestDetectTime"]))

    def is_active(self):
        now = datetime.datetime.now()
        delta = (now - self.get_latest_detection()).total_seconds()

        return delta <= self.delta


class Router(SoapClient):
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


class Siren(_Device):
    def is_playing(self):
        res = self.call("GetSirenAlarmSettings", ModuleID=1, Controller=1)
        return res["IsSounding"] == "true"

    def play(self, sound=Sound.EMERGENCY, volume=100, duration=60):
        ret = self.call(
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
        return self.play(sound=Sound.BEEP, duration=duration, volume=volume)

    def stop(self):
        ret = self.call("SetAlarmDismissed", ModuleID=1, Controller=1)

        if ret["SetAlarmDismissedResult"] != "OK":
            raise MethodCallError(f"Unable to stop. Response: {ret}")


class Water(_Device):
    def is_active(self):
        ret = self.call("GetWaterDetectorState", ModuleID=1)
        return ret.get("IsWater") == "true"
