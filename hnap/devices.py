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

from .config import DeviceConfig
from .const import DEFAULT_MODULE_ID
from .helpers import auth_required
from .soapclient import MethodCallError, SoapClient

_LOGGER = logging.getLogger(__name__)


class DeviceType(Enum):
    CAMERA = "camera"
    MOTION = "motion"
    ROUTER = "router"
    SIREN = "siren"
    WATER = "water"


class Device:
    MODULE_TYPE: str
    DEVICE_TYPE: DeviceType | None = None

    def __init__(
        self,
        config: DeviceConfig,
        *,
        client=None,
        module_id=DEFAULT_MODULE_ID,
    ):
        if not isinstance(config, DeviceConfig):
            raise TypeError("config must be a DeviceConfig")

        self.config = config
        self.client = client or SoapClient(config)
        self.module_id = module_id
        self.device_type = self.DEVICE_TYPE
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

    def reconnect(self):
        """Replace the SOAP client after authenticating a fresh connection."""
        client = SoapClient(self.config)
        client.authenticate()
        self.client = client
        self._info = None


class Camera(Device):
    MODULE_TYPE = "Camera"
    DEVICE_TYPE = DeviceType.CAMERA
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
    DEVICE_TYPE = DeviceType.MOTION

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
    DEVICE_TYPE = DeviceType.ROUTER
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
    DEVICE_TYPE = DeviceType.SIREN

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
    DEVICE_TYPE = DeviceType.WATER

    @auth_required
    def is_active(self):
        ret = self.call("GetWaterDetectorState")
        return ret.get("IsWater") == "true"


_DEVICE_CLASSES = {
    DeviceType.CAMERA: Camera,
    DeviceType.MOTION: Motion,
    DeviceType.ROUTER: Router,
    DeviceType.SIREN: Siren,
    DeviceType.WATER: Water,
}

_DISCOVERY_TYPES = {
    "Audio Renderer": DeviceType.SIREN,
    "Camera": DeviceType.CAMERA,
    "Motion Sensor": DeviceType.MOTION,
}


def DeviceFactory(
    device_type: DeviceType | None = None,
    *,
    config: DeviceConfig,
    module_id: str = DEFAULT_MODULE_ID,
) -> Device:
    """Create a specified device without discovery, or discover its type if None."""
    if not isinstance(config, DeviceConfig):
        raise TypeError("config must be a DeviceConfig")
    if device_type is not None:
        if not isinstance(device_type, DeviceType):
            raise TypeError("device_type must be a DeviceType or None")
    client = SoapClient(config)
    if device_type is not None:
        device = _DEVICE_CLASSES[device_type](
            config, client=client, module_id=module_id
        )
        device.device_type = device_type
        return device

    info = client.device_info()
    module_types = info.get("ModuleTypes", [])
    if isinstance(module_types, str):
        module_types = [module_types]
    elif not isinstance(module_types, list):
        raise TypeError(f"Invalid ModuleTypes value: {module_types!r}")

    device_type = next(
        (
            _DISCOVERY_TYPES[module_type]
            for module_type in _DISCOVERY_TYPES
            if module_type in module_types
        ),
        None,
    )
    if device_type is None:
        raise TypeError(f"Unsupported device module types: {module_types!r}")

    device = _DEVICE_CLASSES[device_type](config, client=client, module_id=module_id)
    device.device_type = device_type
    device._info = info
    return device
