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
import asyncio
import logging
import os
import pprint
import sys
import xml.dom.minidom

import aiohttp

from .config import DeviceConfig
from .soapclient import SoapClient


def _positive_seconds(value):
    seconds = int(value)
    if seconds <= 0:
        raise argparse.ArgumentTypeError("seconds must be greater than zero")
    return seconds


def _create_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--hostname",
        required=True,
        metavar="hostname",
    )
    parser.add_argument(
        "--password",
        required=not bool(os.environ.get("HNAP_PASSWORD")),
        metavar="password",
        default=os.environ.get("HNAP_PASSWORD", ""),
    )
    parser.add_argument(
        "--username",
        default="admin",
        metavar="username",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    call_parser = subparsers.add_parser("call", help="Call a raw SOAP action")
    call_parser.add_argument(
        "method",
        metavar="MethodName",
        help=(
            "If the action requires parameters, pass them with --param, "
            "for example --param Module 1."
        ),
    )
    call_parser.add_argument(
        "--param",
        action="append",
        nargs=2,
        default=[],
        dest="params",
        metavar=("ParamName", "Value"),
        help="Params to pass to call. Multiple params can be passed.",
    )

    monitor_parser = subparsers.add_parser(
        "monitor", help="Poll the device readiness status"
    )
    monitor_parser.add_argument(
        "--seconds",
        type=_positive_seconds,
        default=30,
        metavar="N",
        help="Seconds between readiness checks (default: 30)",
    )
    subparsers.add_parser("inspect", help="Detect device type and show device settings")
    return parser


async def _main():
    logging.basicConfig()
    logging.getLogger("hnap").setLevel(logging.DEBUG)

    args = _create_parser().parse_args()

    config = DeviceConfig(
        hostname=args.hostname,
        password=args.password,
        username=args.username,
    )
    async with SoapClient(config) as client:
        try:
            await client.authenticate()

        except aiohttp.SocketTimeoutError:
            print(
                f"{args.hostname}: read timeout error "
                "(Is device stuck? try rebooting it)",
                file=sys.stderr,
            )
            sys.exit(1)
        except (aiohttp.ClientConnectionError, aiohttp.ConnectionTimeoutError):
            print(
                f"{args.hostname}: connection error (offline device? wrong hostname?)",
                file=sys.stderr,
            )
            sys.exit(1)

        if args.command == "call":
            params = dict(args.params)
            resp = await client.call_raw(args.method, **params)
            if not resp:
                print("Empty (or unsupported) response")
                return

            dom = xml.dom.minidom.parseString(resp)
            print(dom.toprettyxml())

        elif args.command == "monitor":
            while True:
                print(pprint.pformat(await client.call("IsDeviceReady")))
                await asyncio.sleep(args.seconds)

        elif args.command == "inspect":
            info = await client.device_info()
            print(
                "Detected device type(s): "
                f"{pprint.pformat(info.get('ModuleTypes', []))}"
            )
            print(pprint.pformat(info))


def main():
    asyncio.run(_main())


if __name__ == "__main__":
    main()
