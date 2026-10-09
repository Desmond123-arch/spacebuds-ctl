"""A simulated Spacebuds Neo: speaks the Jieli auth handshake and the RCSP ops buds.py uses."""
import os

import buds
import jl_auth

FACTORY = {(1, 1): 0, (2, 1): 0, (1, 2): 5, (2, 2): 5, (1, 3): 3, (2, 3): 4}


class FakeBud:
    """Stands in for the RFCOMM socket. `table` persists across connections, like the real buds."""

    table = dict(FACTORY)
    battery = bytes([100, 99, 0])

    def __init__(self, *args):
        self.rx = b""
        self.challenge = os.urandom(16)
        self.authed = False

    def connect(self, addr):
        pass

    def settimeout(self, t):
        pass

    def close(self):
        pass

    def recv(self, n):
        if not self.rx:
            raise OSError("timed out")
        data, self.rx = self.rx, b""
        return data

    def _reply(self, op, sn, payload):
        self.rx += buds.frame(0x00, op, bytes([0, sn]) + payload)

    def sendall(self, data):
        if not self.authed:
            return self._auth(data)
        op, body = data[4], data[7 : 7 + int.from_bytes(data[5:7], "big")]
        sn = body[0]
        if op == buds.OP_TARGET_INFO:
            self._reply(op, sn, b"\x02\x00")
        elif op == buds.OP_GET_ADV:
            keys = b"".join(
                bytes([b, t, self.table[(b, t)]]) for t in (1, 2, 3) for b in (1, 2)
            )
            self._reply(op, sn, bytes([4, 0]) + self.battery + bytes([len(keys) + 1, 2]) + keys)
        elif op == buds.OP_SET_ADV:
            assert body[1] == 0x13 and body[2] == 0x02 and len(body) == 21
            v = body[3:]
            for i in range(0, 18, 3):
                self.table[(v[i], v[i + 1])] = v[i + 2]
            self._reply(op, sn, b"")

    def _auth(self, data):
        if data[0] == 0:
            self.rx += jl_auth.respond(data[1:])
        elif data == b"\x02pass":
            self.rx += b"\x00" + self.challenge
        elif data[0] == 1:
            assert data == jl_auth.respond(self.challenge), "phone answered our challenge wrongly"
            self.rx += b"\x02pass"
            self.authed = True
