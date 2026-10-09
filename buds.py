"""buds: control Oraimo Spacebuds Neo (Jieli RCSP over Bluetooth RFCOMM).

Run with native Windows Python 3.9+ (WSL has no Bluetooth). Pair the buds with
the PC first and disconnect them from your phone / close the Oraimo app.

  python buds.py status
  python buds.py gestures
  python buds.py set --single playpause --double next --triple prev
  python buds.py set --bud left --double none
  python buds.py reset
  python buds.py --raw status        # also print every frame
  python buds.py --json status       # machine-readable, for buds_tui.py
"""
import argparse
import json
import os
import socket
import sys
import time

import jl_auth

DEFAULT_MAC = "24:DF:17:48:32:02"
CHANNEL = 1

BUDS = {"left": 1, "right": 2}
TAPS = {"single": 1, "double": 2, "triple": 3}
ACTIONS = {"none": 0, "prev": 3, "next": 4, "playpause": 5}  # confirmed by testing on the buds
ACTION_NAMES = {v: k for k, v in ACTIONS.items()}
FACTORY = {
    ("left", "single"): 0, ("left", "double"): 5, ("left", "triple"): 3,
    ("right", "single"): 0, ("right", "double"): 5, ("right", "triple"): 4,
}

OP_TARGET_INFO, OP_GET_ADV, OP_SET_ADV = 0x03, 0xC1, 0xC0
ATTR_BATTERY, ATTR_KEYS = 0x00, 0x02


class BudsError(Exception):
    pass


def frame(flag, op, body):
    return b"\xfe\xdc\xba" + bytes([flag, op]) + len(body).to_bytes(2, "big") + body + b"\xef"


class Buds:
    def __init__(self, mac, channel=CHANNEL, raw=False):
        self.raw = raw
        self.sn = 0x50
        self.buf = b""
        self.sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        try:
            self.sock.connect((mac, channel))
        except OSError as e:
            raise BudsError(
                f"could not connect to {mac} ({e}). Are the buds paired with this PC, "
                "out of their case, and disconnected from your phone?"
            ) from e
        self._authenticate()
        self.call(OP_TARGET_INFO, b"\xff\xff\xff\xff\x00")  # the app always sends this first

    def close(self):
        self.sock.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _recv(self):
        self.sock.settimeout(0.2)
        try:
            chunk = self.sock.recv(4096)
        except OSError:
            return b""
        if chunk and self.raw:
            print("  rx", chunk.hex())
        return chunk

    def _authenticate(self, timeout=5.0):
        """Jieli mutual challenge/response; the buds ignore RCSP until it passes."""
        if self.raw:
            print("  auth: start")
        self.sock.sendall(jl_auth.new_challenge())
        buf, end = b"", time.time() + timeout
        while time.time() < end:
            buf += self._recv()
            while buf:
                need = {0: 17, 1: 17, 2: 5}.get(buf[0])
                if need is None:
                    raise BudsError(f"unexpected byte {buf[0]:#x} during authentication")
                if len(buf) < need:
                    break
                msg, buf = buf[:need], buf[need:]
                if msg[0] == 0:
                    self.sock.sendall(jl_auth.respond(msg[1:]))
                elif msg[0] == 1:
                    self.sock.sendall(b"\x02pass")
                elif msg == b"\x02pass":
                    return
                else:
                    raise BudsError("authentication rejected by the buds")
        raise BudsError("authentication timed out")

    def call(self, op, payload=b"", wait=2.0):
        self.sn = (self.sn + 1) & 0xFF
        out = frame(0xC0, op, bytes([self.sn]) + payload)
        if self.raw:
            print("  tx", out.hex())
        self.sock.sendall(out)
        end = time.time() + wait
        while time.time() < end:
            for flag, rop, body in self._frames():
                if flag == 0x00 and rop == op and body[1:2] == bytes([self.sn]):
                    if body[0] != 0:
                        raise BudsError(f"buds rejected op {op:#x} (status {body[0]:#x})")
                    return body[2:]
        raise BudsError(f"no reply to op {op:#x}")

    def _frames(self):
        self.buf += self._recv()
        out = []
        while True:
            i = self.buf.find(b"\xfe\xdc\xba")
            if i < 0 or len(self.buf) < i + 8:
                break
            ln = int.from_bytes(self.buf[i + 5 : i + 7], "big")
            if len(self.buf) < i + 8 + ln:
                break
            out.append((self.buf[i + 3], self.buf[i + 4], self.buf[i + 7 : i + 7 + ln]))
            self.buf = self.buf[i + 8 + ln :]
        return out

    def attributes(self):
        """Read the buds' attribute list as {type: value bytes}."""
        p, attrs = self.call(OP_GET_ADV, b"\xff\xff\xff\xff"), {}
        while len(p) > 1:
            n = p[0]
            if n < 1 or len(p) < 1 + n:
                break
            attrs[p[1]] = p[2 : 1 + n]
            p = p[1 + n :]
        return attrs

    def gestures(self):
        v = self.attributes().get(ATTR_KEYS, b"")
        table = {}
        names_b = {n: b for b, n in BUDS.items()}
        names_t = {n: t for t, n in TAPS.items()}
        for i in range(0, len(v) - 2, 3):
            bud, tap, fn = v[i : i + 3]
            if bud in names_b and tap in names_t:
                table[(names_b[bud], names_t[tap])] = fn
        return table

    def set_gestures(self, table):
        entries = b"".join(
            bytes([BUDS[bud], TAPS[tap], fn])
            for bud in ("right", "left")
            for tap in ("single", "double", "triple")
            for fn in [table[(bud, tap)]]
        )
        self.call(OP_SET_ADV, bytes([len(entries) + 1, ATTR_KEYS]) + entries)


def action_name(fn):
    return ACTION_NAMES.get(fn, f"code {fn}")


def print_gestures(table):
    print(f"{'':6}{'single':>12}{'double':>12}{'triple':>12}")
    for bud in BUDS:
        cells = [action_name(table[(bud, t)]) if (bud, t) in table else "?" for t in TAPS]
        print(f"{bud:6}" + "".join(f"{c:>12}" for c in cells))


def parse_action(text):
    if text in ACTIONS:
        return ACTIONS[text]
    try:
        return int(text, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r}: use one of {', '.join(ACTIONS)} or a number")


def gesture_dict(table):
    return {bud: {tap: table[(bud, tap)] for tap in TAPS if (bud, tap) in table} for bud in BUDS}


def battery_dict(attrs):
    bat = attrs.get(ATTR_BATTERY)
    if not bat or len(bat) < 3:
        return None
    # inferred from the capture (100, 100, 0): left, right, case; bit 7 = charging
    return {
        name: {"percent": bat[i] & 0x7F, "charging": bool(bat[i] & 0x80)}
        for i, name in enumerate(("left", "right", "case"))
    }


def cmd_status(b, a):
    return {"battery": battery_dict(b.attributes()), "gestures": gesture_dict(b.gestures())}


def cmd_gestures(b, a):
    return {"gestures": gesture_dict(b.gestures())}


def cmd_set(b, a):
    chosen = {"single": a.single, "double": a.double, "triple": a.triple}
    if all(v is None for v in chosen.values()):
        raise BudsError("nothing to set: pass --single, --double and/or --triple")
    table = b.gestures()
    if len(table) != 6:
        raise BudsError("could not read the current gesture table; not writing")
    for bud in (BUDS if a.bud == "both" else [a.bud]):
        for tap, fn in chosen.items():
            if fn is not None:
                table[(bud, tap)] = fn
    b.set_gestures(table)
    return {"message": "written; read back:", "gestures": gesture_dict(b.gestures())}


def cmd_reset(b, a):
    b.set_gestures(dict(FACTORY))
    return {"message": "restored factory gestures; read back:", "gestures": gesture_dict(b.gestures())}


def render(data):
    if data.get("message"):
        print(data["message"])
    bat = data.get("battery")
    if bat:
        part = lambda x: f"{x['percent']}%" + (" (charging)" if x["charging"] else "")
        print(f"battery  left {part(bat['left'])}  right {part(bat['right'])}  case {part(bat['case'])}")
    g = data["gestures"]
    if "battery" in data:
        print("gestures")
    print_gestures({(bud, tap): fn for bud, taps in g.items() for tap, fn in taps.items()})


def build_parser():
    ap = argparse.ArgumentParser(prog="buds", description=__doc__.split("\n\n")[0])
    ap.add_argument("--mac", default=os.environ.get("BUDS_MAC", DEFAULT_MAC), help="buds address (or set BUDS_MAC)")
    ap.add_argument("--channel", type=int, default=CHANNEL)
    ap.add_argument("--raw", action="store_true", help="print every frame")
    ap.add_argument("--json", action="store_true", help="machine-readable output (used by buds_tui.py)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="battery and gestures").set_defaults(fn=cmd_status)
    sub.add_parser("gestures", help="show gestures").set_defaults(fn=cmd_gestures)
    s = sub.add_parser("set", help="change gestures, leaving unnamed ones alone")
    s.add_argument("--bud", choices=["left", "right", "both"], default="both")
    for tap in TAPS:
        s.add_argument(f"--{tap}", type=parse_action, metavar="ACTION", help=f"{tap} tap: {', '.join(ACTIONS)} or a number")
    s.set_defaults(fn=cmd_set)
    sub.add_parser("reset", help="restore factory gestures").set_defaults(fn=cmd_reset)
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        with Buds(a.mac, a.channel, a.raw and not a.json) as b:
            data = a.fn(b, a)
    except BudsError as e:
        if a.json:
            print(json.dumps({"error": str(e)}))
            sys.exit(1)
        sys.exit(f"error: {e}")
    print(json.dumps(data)) if a.json else render(data)


if __name__ == "__main__":
    main()
