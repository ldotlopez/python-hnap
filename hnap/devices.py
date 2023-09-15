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


import logging
from datetime import datetime
from enum import Enum

from .const import DEFAULT_MODULE_ID, DEFAULT_PORT, DEFAULT_USERNAME
from .helpers import auth_required
from .soapclient import MethodCallError, SoapClient

_LOGGER = logging.getLogger(__name__)


def DeviceFactory(
    *,
    client=None,
    hostname=None,
    password=None,
    username=DEFAULT_USERNAME,
    port=DEFAULT_PORT,
):
    client = client or SoapClient(
        hostname=hostname, password=password, username=username, port=port
    )
    info = client.device_info()

    module_types = info["ModuleTypes"]
    if not isinstance(module_types, list):
        module_types = [module_types]

    if "Audio Renderer" in module_types:
        cls = Siren

    elif "Camera" in module_types:
        # Other posible values for camera (needs testing):
        # 'Optical Recognition', 'Environmental Sensor', 'Camera'
        cls = Camera

    elif "Motion Sensor" in module_types:
        cls = Motion

    else:
        raise TypeError(module_types)

    return cls(client=client)


class Device:
    MODULE_TYPE: str

    def __init__(
        self,
        *,
        client=None,
        hostname=None,
        password=None,
        username=DEFAULT_USERNAME,
        port=DEFAULT_PORT,
        module_id=DEFAULT_MODULE_ID,
    ):
        self.client = client or SoapClient(
            hostname=hostname, password=password, username=username, port=port
        )
        self.module_id = module_id

        self._info = None

    @property
    def info(self):
        if not self._info:
            self._info = self.client.device_info()

        return self._info

    def call(self, *args, **kwargs):
        kwargs["ModuleID"] = self.module_id
        return self.client.call(*args, **kwargs)

    def is_authenticated(self):
        return self.client.is_authenticated()

    def authenticate(self):
        return self.client.authenticate()


class Camera(Device):
    MODULE_TYPE = "Camera"
    DEFAULT_SCHEMA = "http://"
    DEFAULT_STREAM_PATH = "/play1.sdp"
    DEFAULT_PICTURE_PATH = "/image/jpeg.cgi"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._base_url = (
            {self.DEFAULT_SCHEMA}
            + f"{self.client.username.lower()}:{self.client.password}@"
            + f"{self.client.hostname}:{self.client.port}"
        )

    @property
    def stream_url(self):
        return f"{self._base_url}{self.DEFAULT_STREAM_PATH}"

    @property
    def picture_url(self):
        return f"{self._base_url}{self.DEFAULT_PICTURE_PATH}"


class Motion(Device):
    MODULE_TYPE = "Motion Sensor"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._backoff = None

    @property
    def backoff(self):
        if self._backoff is None:
            resp = self.call("GetMotionDetectorSettings")
            try:
                self._backoff = int(resp["Backoff"])
            except (KeyError, ValueError, TypeError):
                # Return the default value for tested devices but don't store
                # to force retry
                return 30

        return self._backoff

    # @backoff.setter
    # def backoff(self, seconds):
    #     self.call(
    #         "SetMotionDetectorSettings", Backoff=self._backoff
    #     )
    #     _LOGGER.warning("set backoff property has no effect")

    # def authenticate(self):
    #     super().authenticate()

    #     res = self.call("GetMotionDetectorSettings")
    #     try:
    #         self._backoff = int(res["Backoff"])
    #     except (ValueError, TypeError, KeyError):
    #         _LOGGER.warning("Unable to get delta from device")

    @auth_required
    def get_latest_detection(self):
        res = self.call("GetLatestDetection")
        return datetime.fromtimestamp(float(res["LatestDetectTime"]))

    @auth_required
    def is_active(self):
        now = datetime.now()
        diff = (now - self.get_latest_detection()).total_seconds()

        return diff <= self.backoff


class Router(Device):
    # NOT tested
    # See https://github.com/waffelheld/dlink-device-tracker/blob/master/custom_components/dlink_device_tracker/dlink_hnap.py#L95  # noqa: E501
    MODULE_TYPE = "check-module-types-for-router"

    @auth_required
    def get_clients(self):
        res = self.call("GetClientInfo")
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


class SirenSound(Enum):
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


class Siren(Device):
    MODULE_TYPE = "Audio Renderer"

    @auth_required
    def is_playing(self):
        res = self.call("GetSirenAlarmSettings")
        return res["IsSounding"] == "true"

    @auth_required
    def play(self, sound=SirenSound.EMERGENCY, volume=100, duration=60):
        ret = self.call(
            "SetSoundPlay",
            SoundType=sound.value,
            Volume=volume,
            Duration=duration,
        )
        if ret["SetSoundPlayResult"] != "OK":
            raise MethodCallError(f"Unable to play. Response: {ret}")

    @auth_required
    def beep(self, volume=100, duration=1):
        return self.play(sound=SirenSound.BEEP, duration=duration, volume=volume)

    @auth_required
    def stop(self):
        ret = self.call("SetAlarmDismissed")

        if ret["SetAlarmDismissedResult"] != "OK":
            raise MethodCallError(f"Unable to stop. Response: {ret}")


class Water(Device):
    # NOT tested
    MODULE_TYPE = "check-module-types-for-water-detector"

    @auth_required
    def is_active(self):
        ret = self.call("GetWaterDetectorState")
        return ret.get("IsWater") == "true"
