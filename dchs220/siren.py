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


import enum
from .soapclient import SoapClient, MethodCallError


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
        for c in ['-', ' ', '.']:
            s = s.replace(c, '_')

        return getattr(cls, s)


class Siren(SoapClient):
    def is_playing(self):
        body = self._build_method_envelope(
            "GetSirenAlarmSettings",
            ("<ModuleID>1</ModuleID>" "<Controller>1</Controller>"),
        )
        res = self.execute_and_parse(
            "GetSirenAlarmSettings", "IsSounding", body
        )
        return res == "true"

    def play(self, sound=Sound.EMERGENCY, volume=100, duration=60):
        ret = self.execute_and_parse(
            "SetSoundPlay",
            "SetSoundPlayResult",
            self._build_method_envelope(
                "SetSoundPlay",
                f"""
                <ModuleID>1</ModuleID>
                <Controller>1</Controller>
                <SoundType>{sound.value}</SoundType>
                <Volume>{volume}</Volume>
                <Duration>{duration}</Duration>
            """,
            ),
        )

        if ret != "OK":
            raise MethodCallError(f"Unable to play. Response: {ret}")

    def beep(self, volume=100, duration=1):
        return self.play(sound=Sound.BEEP, duration=duration, volume=volume)

    def stop(self):
        return self.execute_and_parse(
            "SetAlarmDismissed",
            "SetAlarmDismissedResult",
            self._build_method_envelope(
                "SetAlarmDismissed",
                """
                <ModuleID>1</ModuleID>
                <Controller>1</Controller>
            """,
            ),
        )
