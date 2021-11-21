import enum
from .soapclient import SoapClient


class Sound(enum.Enum):
    EMERGENCY = 1
    FIRE = 2
    AMBULANCE = 3
    POLICE = 4
    DOOR_CHIME = 5
    BEEP = 6

    @classmethod
    def fromstring(cls, s):
        return getattr(cls, s.replace('-', '_').upper())


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
        if ret != 'OK':
            raise Exception(ret)

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
