# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
import unittest
from unittest.mock import Mock, patch

from gi.repository import GLib
from powertoys_linux.desktop import ColorRequest


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.connection = Mock()
        self.connection.get_unique_name.return_value = ":1.999"
        self.connection.signal_subscribe.return_value = 123
        self.callback = Mock()
        with patch("powertoys_linux.desktop.Gio.bus_get_sync", return_value=self.connection):
            self.request = ColorRequest(self.callback)
        self.addCleanup(self.request.cancel)

    def test_subscribes_to_expected_path_before_calling(self):
        methods = [call[0] for call in self.connection.mock_calls]
        self.assertLess(methods.index("signal_subscribe"), methods.index("call"))
        self.assertTrue(self.request.path.startswith("/org/freedesktop/portal/desktop/request/1_999/powertoys_"))
        self.assertEqual(self.connection.call.call_args[0][3], "PickColor")

    def test_response_and_cleanup(self):
        self.request.response(None, None, None, None, None,
                              GLib.Variant("(ua{sv})", (0, {"color": GLib.Variant("(ddd)", (1.0, 0.0, 0.5))})))
        self.callback.assert_called_once_with((1.0, 0.0, 0.5), None)
        self.connection.signal_unsubscribe.assert_called_once_with(123)
        self.assertFalse(self.request.active)
        self.assertEqual(self.request.timer, 0)

    def test_invalid_response_and_user_cancel(self):
        self.request.response(None, None, None, None, None, GLib.Variant("(ua{sv})", (0, {})))
        self.assertIsNone(self.callback.call_args[0][0])
        self.assertIn("valid color", self.callback.call_args[0][1])

    def test_cancel_closes_request_and_calls_callback_once(self):
        self.request.cancel()
        self.request.cancel()
        self.assertEqual(self.connection.call.call_args[0][3], "Close")
        self.callback.assert_called_once_with(None, "Color picking cancelled.")
