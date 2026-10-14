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

OUTPUT_TMPL = """
Device info
===========
{info}

Device actions
==============
{device_actions}

Module actions
==============
{module_actions}
"""


async def _main():
    logging.basicConfig()
    logging.getLogger("hnap").setLevel(logging.DEBUG)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--hostname",
        required=True,
        metavar="hostname",
    )
    parser.add_argument(
        "--password",
        required=True,
        metavar="password",
        default=os.environ.get("HNAP_PASSWORD", ""),
    )
    parser.add_argument(
        "--username",
        default="admin",
        metavar="username",
    )
    parser.add_argument(
        "--call",
        nargs=1,
        default=[],
        metavar="MethodName",
        help=(
            "If you are calling a SOAP action you must pass, at least, "
            "`--param Module 1` and, maybe, `--param Controller 1`."
        ),
    )
    parser.add_argument(
        "--param",
        action="append",
        nargs=2,
        default=[],
        dest="params",
        metavar=("ParamName", "Value"),
        help="Params to pass to call. Multiple params can be passed.",
    )
    args = parser.parse_args()

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

        if args.call:
            params = dict(args.params)
            resp = await client.call_raw(args.call[0], **params)
            if not resp:
                print("Empty (or unsupported) response")
                return

            dom = xml.dom.minidom.parseString(resp)
            print(dom.toprettyxml())

        else:
            print(
                OUTPUT_TMPL.format(
                    info=pprint.pformat(await client.device_info()),
                    device_actions=pprint.pformat(await client.device_actions()),
                    module_actions=pprint.pformat(await client.module_actions()),
                ).strip()
            )


def main():
    asyncio.run(_main())


if __name__ == "__main__":
    main()
