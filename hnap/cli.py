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


import argparse
import os

from . import Siren, Sound


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
