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

from datetime import datetime
from enum import Enum

import aiohttp

from .config import DeviceConfig
from .const import DEFAULT_MODULE_ID
from .helpers import auth_required
from .soapclient import MethodCallError, SoapClient


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
        soap_client: SoapClient | None = None,
        http_client: aiohttp.ClientSession | None = None,
        module_id=DEFAULT_MODULE_ID,
    ):
        if not isinstance(config, DeviceConfig):
            raise TypeError("config must be a DeviceConfig")
        if soap_client is not None and http_client is not None:
            if soap_client.http_client is not http_client:
                raise ValueError("soap_client and http_client must use the same client")

        self.config = config
        self.soap_client = (
            soap_client
            if soap_client is not None
            else SoapClient(config, http_client=http_client)
        )
        self.module_id = module_id
        self.device_type = self.DEVICE_TYPE
        self._info = None

    async def get_info(self):
        if self._info is None:
            self._info = await self.soap_client.device_info()
        return self._info

    async def call(self, *args, **kwargs):
        kwargs["ModuleID"] = self.module_id
        return await self.soap_client.call(*args, **kwargs)

    async def is_authenticated(self):
        return await self.soap_client.is_authenticated()

    async def authenticate(self):
        return await self.soap_client.authenticate()

    @property
    def http_client(self):
        return self.soap_client.http_client

    async def reconnect(self):
        """Replace the SOAP client after authenticating a fresh connection."""
        previous_soap_client = self.soap_client
        http_client = await previous_soap_client.start()
        soap_client = SoapClient(self.config, http_client=http_client)
        await soap_client.authenticate()
        soap_client._owns_http_client = previous_soap_client._owns_http_client
        previous_soap_client._owns_http_client = False
        self.soap_client = soap_client
        self._info = None

    async def close(self):
        await self.soap_client.close()

    async def __aenter__(self):
        await self.soap_client.start()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.close()


class Camera(Device):
    MODULE_TYPE = "Camera"
    DEVICE_TYPE = DeviceType.CAMERA
    DEFAULT_SCHEMA = "http://"
    DEFAULT_STREAM_PATH = "/play1.sdp"
    DEFAULT_PICTURE_PATH = "/image/jpeg.cgi"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._base_url = (
            self.DEFAULT_SCHEMA
            + f"{self.soap_client.username.lower()}:{self.soap_client.password}@"
            + f"{self.soap_client.hostname}:{self.soap_client.port}"
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

    async def get_backoff(self):
        if self._backoff is None:
            response = await self.call("GetMotionDetectorSettings")
            try:
                self._backoff = int(response["Backoff"])
            except (KeyError, ValueError, TypeError):
                return 30
        return self._backoff

    @auth_required
    async def get_latest_detection(self):
        response = await self.call("GetLatestDetection")
        return datetime.fromtimestamp(float(response["LatestDetectTime"]))

    @auth_required
    async def is_active(self):
        difference = (
            datetime.now() - await self.get_latest_detection()
        ).total_seconds()
        return difference <= await self.get_backoff()


class Router(Device):
    DEVICE_TYPE = DeviceType.ROUTER
    MODULE_TYPE = "check-module-types-for-router"

    @auth_required
    async def get_clients(self):
        response = await self.call("GetClientInfo")
        clients = response["ClientInfoLists"]["ClientInfo"]
        return [
            {
                "name": client["DeviceName"],
                "nickName": client["NickName"],
                "is_connected": int(client["Type"] != "OFFLINE"),
                "mac": client["MacAddress"],
            }
            for client in clients
        ]


class SirenSound(Enum):
    EMERGENCY = 1
    FIRE = 2
    AMBULANCE = 3
    POLICE = 4
    DOOR_CHIME = 5
    BEEP = 6

    @classmethod
    def fromstring(cls, value):
        value = value.upper()
        for separator in ("-", " ", "."):
            value = value.replace(separator, "_")
        return getattr(cls, value)


class Siren(Device):
    MODULE_TYPE = "Audio Renderer"
    DEVICE_TYPE = DeviceType.SIREN

    @auth_required
    async def is_playing(self):
        response = await self.call("GetSirenAlarmSettings")
        return response["IsSounding"] == "true"

    @auth_required
    async def play(self, sound=SirenSound.EMERGENCY, volume=100, duration=60):
        response = await self.call(
            "SetSoundPlay",
            SoundType=sound.value,
            Volume=volume,
            Duration=duration,
        )
        if response["SetSoundPlayResult"] != "OK":
            raise MethodCallError(f"Unable to play. Response: {response}")

    async def beep(self, volume=100, duration=1):
        return await self.play(sound=SirenSound.BEEP, duration=duration, volume=volume)

    @auth_required
    async def stop(self):
        response = await self.call("SetAlarmDismissed")
        if response["SetAlarmDismissedResult"] != "OK":
            raise MethodCallError(f"Unable to stop. Response: {response}")


class Water(Device):
    MODULE_TYPE = "check-module-types-for-water-detector"
    DEVICE_TYPE = DeviceType.WATER

    @auth_required
    async def is_active(self):
        response = await self.call("GetWaterDetectorState")
        return response.get("IsWater") == "true"


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


def _resolve_discovered_type(info):
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
    return device_type


async def DeviceFactory(
    device_type: DeviceType | None = None,
    *,
    config: DeviceConfig,
    module_id: str = DEFAULT_MODULE_ID,
    http_client=None,
) -> Device:
    """Create a device or discover its type using HNAP."""
    if not isinstance(config, DeviceConfig):
        raise TypeError("config must be a DeviceConfig")
    if device_type is not None and not isinstance(device_type, DeviceType):
        raise TypeError("device_type must be a DeviceType or None")

    soap_client = SoapClient(config, http_client=http_client)
    try:
        info = None
        if device_type is None:
            info = await soap_client.device_info()
            device_type = _resolve_discovered_type(info)
        device = _DEVICE_CLASSES[device_type](
            config, soap_client=soap_client, module_id=module_id
        )
    except BaseException:
        await soap_client.close()
        raise

    device.device_type = device_type
    device._info = info
    return device
