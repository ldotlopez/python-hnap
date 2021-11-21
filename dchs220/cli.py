#!/usr/bin/env python3

import argparse
import os

from dchs220 import Siren, Sound


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hostname", required=True)
    parser.add_argument(
        "--pin", default=os.environ.get("SCHS220_PIN", ""), required=True
    )
    parser.add_argument("--username", default="admin")

    subparser = parser.add_subparsers(dest="command")
    beep = subparser.add_parser("beep")
    play = subparser.add_parser("play")
    status = subparser.add_parser("status")  # noqa
    stop = subparser.add_parser("stop")  # noqa

    beep.add_argument("-v", "--volume", default=1, type=int)
    play.add_argument("-v", "--volume", default=1, type=int)
    play.add_argument("-s", "--sound", default="beep", type=str)
    play.add_argument("-d", "--duration", default=5, type=int)

    args = parser.parse_args()

    siren = Siren(hostname=args.hostname, pin=args.pin)
    siren.login()

    if args.command == "beep":
        siren.beep(volume=args.volume)

    elif args.command == "play":
        siren.play(
            sound=Sound.fromstring(args.sound),
            volume=args.volume,
            duration=args.duration,
        )

    elif args.command == "status":
        print("playing" if siren.is_playing() else "not playing")

    elif args.command == "stop":
        siren.stop()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
