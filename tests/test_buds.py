import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import buds  # noqa: E402
import fake_bud  # noqa: E402
import jl_auth  # noqa: E402


def run(*argv):
    """Run the CLI in --json mode against the simulated buds."""
    out = io.StringIO()
    with mock.patch.object(buds.socket, "socket", fake_bud.FakeBud), contextlib.redirect_stdout(out):
        buds.main(["--json", *argv])
    return json.loads(out.getvalue())


class AuthTest(unittest.TestCase):
    # Challenge/response pairs captured from real Spacebuds Neo traffic.
    PAIRS = [
        ("dd742b3e96131de73a0148f86d203cab", "31d28904d9f404cd8b4dc8bc4643ae5d"),
        ("3baf31eb359a85a1dd29ca47c3bae91b", "927da5b79483a453bb0a61ca2407a5dd"),
    ]

    def test_matches_captured_responses(self):
        for challenge, response in self.PAIRS:
            self.assertEqual(jl_auth.respond(bytes.fromhex(challenge)).hex(), "01" + response)


class CliTest(unittest.TestCase):
    def setUp(self):
        fake_bud.FakeBud.table = dict(fake_bud.FACTORY)

    def test_status_reports_battery_and_gestures(self):
        data = run("status")
        self.assertEqual(data["battery"]["left"], {"percent": 100, "charging": False})
        self.assertEqual(data["gestures"]["left"], {"single": 0, "double": 5, "triple": 3})
        self.assertEqual(data["gestures"]["right"], {"single": 0, "double": 5, "triple": 4})

    def test_set_changes_only_the_named_slots(self):
        data = run("set", "--bud", "left", "--double", "none")
        self.assertEqual(data["gestures"]["left"], {"single": 0, "double": 0, "triple": 3})
        self.assertEqual(data["gestures"]["right"], {"single": 0, "double": 5, "triple": 4})

    def test_set_all_taps_on_both_buds(self):
        data = run("set", "--single", "playpause", "--double", "next", "--triple", "prev")
        for bud in ("left", "right"):
            self.assertEqual(data["gestures"][bud], {"single": 5, "double": 4, "triple": 3})

    def test_reset_restores_factory(self):
        run("set", "--single", "playpause")
        data = run("reset")
        self.assertEqual(data["gestures"]["right"], {"single": 0, "double": 5, "triple": 4})

    def test_set_without_slots_is_an_error(self):
        with self.assertRaises(SystemExit):
            run("set")


if __name__ == "__main__":
    unittest.main()
