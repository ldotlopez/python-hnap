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
import logging
import os
import pprint
import sys
import xml.dom.minidom

import requests

from .soapclient import SoapClient

OUTPUT_TMPL = """
Device info
===========
{info}

Device actions
==============
{device_actions}

SOAP actions
==============
{soap_actions}
"""


def main():
    logging.basicConfig()
    logging.getLogger("hnap").setLevel(logging.DEBUG)

    parser = argparse.ArgumentParser()
    parser.add_argument("--hostname", required=True)
    parser.add_argument(
        "--password",
        default=os.environ.get("HNAP_PASSWORD", ""),
        required=True,
    )
    parser.add_argument("--username", default="admin")
    parser.add_argument("--call", nargs=1, default=[])
    parser.add_argument("--params", nargs=2, action="append", default=[])
    args = parser.parse_args()

    if len(args.call) > 1:
        print("Error: Only on call is allowed", file=sys.stderr)
        return 1

    client = SoapClient(
        hostname=args.hostname,
        username=args.username,
        password=args.password,
    )

    try:
        client.authenticate()

    except requests.ReadTimeout:
        print(
            f"{args.hostname}: read timeout error "
            "(Is device stuck? try rebooting it)",
            file=sys.stderr,
        )
        sys.exit(1)
    except requests.ConnectionError:
        print(
            f"{args.hostname}: connection error (offline device? wrong hostname?)",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.call:
        params = dict(args.params)
        resp = client.call_raw(args.call[0], **params)
        if not resp:
            print("Empty (or unsupported) response")
            return

        dom = xml.dom.minidom.parseString(resp)
        print(dom.toprettyxml())

    else:
        print(
            OUTPUT_TMPL.format(
                info=pprint.pformat(client.device_info()),
                soap_actions=pprint.pformat(client.soap_actions()),
                device_actions=pprint.pformat(client.device_actions()),
            ).strip()
        )


if __name__ == "__main__":
    main()
