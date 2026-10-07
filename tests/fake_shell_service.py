"""A fake GNOME Shell extension on the session bus, for testing the real D-Bus transport.

Run it with a Python that has PyGObject:  python3.12 tests/fake_shell_service.py scenario.json
The scenario file holds the keyword arguments of FakeShell. It prints "ready" once the name is owned.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi  # noqa: E402

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from cascade_windows import shell_protocol as protocol  # noqa: E402
from tests.fake_shell import FakeShell  # noqa: E402

XML = """
<node>
  <interface name="%s">
    <method name="GetState"><arg type="s" direction="out"/></method>
    <method name="Apply"><arg type="s" direction="in"/><arg type="s" direction="out"/></method>
  </interface>
</node>
""" % protocol.INTERFACE


def main():
    with open(sys.argv[1]) as handle:
        scenario = json.load(handle)
    shell = FakeShell(**scenario)
    info = Gio.DBusNodeInfo.new_for_xml(XML)

    def on_call(connection, sender, path, interface, method, parameters, invocation):
        if method == "GetState":
            invocation.return_value(GLib.Variant("(s)", (json.dumps(shell.get_state()),)))
        else:
            operations = json.loads(parameters.unpack()[0])
            invocation.return_value(GLib.Variant("(s)", (json.dumps(shell.apply(operations)),)))

    def on_bus(connection, name):
        connection.register_object(protocol.OBJECT_PATH, info.interfaces[0], on_call, None, None)

    def on_name(connection, name):
        print("ready", flush=True)

    Gio.bus_own_name(Gio.BusType.SESSION, protocol.BUS_NAME, Gio.BusNameOwnerFlags.NONE,
                     on_bus, on_name, None)
    GLib.MainLoop().run()


main()
