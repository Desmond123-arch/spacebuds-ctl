"""buds_tui: full-screen terminal UI for Oraimo Spacebuds Neo, meant for a tmux pane.

Run it from WSL. Bluetooth only works on Windows, so every action shells out to
Windows Python running buds.py (kept next to this file) with --json.

  python3 buds_tui.py

Keys:  arrows / hjkl  move      n / + / ]  next action     p / - / [  previous action
       w  write changes         u  discard changes         r  refresh
       R  factory reset         q  quit

Override the backend with BUDS_CMD, e.g. BUDS_CMD='python.exe C:\\path\\buds.py'.
"""
import curses
import json
import os
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUDS = ("left", "right")
TAPS = ("single", "double", "triple")
CYCLE = (0, 3, 4, 5)
NAMES = {0: "none", 3: "prev", 4: "next", 5: "play/pause"}


def backend_cmd():
    if os.environ.get("BUDS_CMD"):
        return shlex.split(os.environ["BUDS_CMD"], posix=True)
    script = subprocess.run(["wslpath", "-w", os.path.join(HERE, "buds.py")], capture_output=True, text=True).stdout.strip()
    return ["python.exe", script or "buds.py"]


def call(args):
    """Run the backend; returns (data, error)."""
    try:
        p = subprocess.run(backend_cmd() + ["--json"] + args, capture_output=True, text=True, timeout=40)
    except FileNotFoundError as e:
        return None, f"cannot run backend: {e}"
    except subprocess.TimeoutExpired:
        return None, "timed out talking to the buds"
    lines = [l for l in p.stdout.splitlines() if l.strip().startswith("{")]
    if lines:
        data = json.loads(lines[-1])
        return (None, data["error"]) if "error" in data else (data, None)
    tail = (p.stderr.strip().splitlines() or ["no output from backend"])[-1]
    return None, tail


def action_name(code):
    return NAMES.get(code, f"code {code}")


def cycle(code, step):
    if code not in CYCLE:
        return CYCLE[0] if step > 0 else CYCLE[-1]
    return CYCLE[(CYCLE.index(code) + step) % len(CYCLE)]


class App:
    def __init__(self, scr):
        self.scr = scr
        self.gestures = {}  # bud -> tap -> code, as last read from the buds
        self.pending = {}  # (bud, tap) -> code, not yet written
        self.battery = None
        self.row = self.col = 0
        self.msg = "starting..."
        self.err = False
        self.busy = False

    def value(self, bud, tap):
        if (bud, tap) in self.pending:
            return self.pending[(bud, tap)]
        return self.gestures.get(bud, {}).get(tap)

    def run(self, args, working):
        self.msg, self.err, self.busy = working, False, True
        self.draw()
        data, error = call(args)
        self.busy = False
        if error:
            self.msg, self.err = error, True
            return None
        if data.get("gestures"):
            self.gestures = data["gestures"]
        if data.get("battery"):
            self.battery = data["battery"]
        return data

    def refresh(self):
        if self.run(["status"], "reading from the buds..."):
            self.msg = "ok"

    def write(self):
        if not self.pending:
            self.msg = "nothing to write"
            return
        for bud in BUDS:
            changes = {t: c for (b, t), c in self.pending.items() if b == bud}
            if not changes:
                continue
            args = ["set", "--bud", bud] + [x for t, c in changes.items() for x in (f"--{t}", str(c))]
            if not self.run(args, f"writing {bud} bud..."):
                return
        self.pending.clear()
        self.msg = "written"

    def reset(self):
        self.msg = "factory reset: press y to confirm"
        self.draw()
        if self.scr.getch() in (ord("y"), ord("Y")):
            if self.run(["reset"], "restoring factory gestures..."):
                self.pending.clear()
                self.msg = "factory gestures restored"
        else:
            self.msg = "reset cancelled"

    def draw(self):
        scr = self.scr
        scr.erase()
        h, w = scr.getmaxyx()
        put = lambda y, x, text, attr=0: y < h - 1 and scr.addnstr(y, x, text, max(0, w - x - 1), attr)
        put(0, 1, "Spacebuds Neo", curses.A_BOLD)
        if self.battery:
            parts = []
            for k in ("left", "right", "case"):
                b = self.battery[k]
                parts.append(f"{k[0].upper()} {b['percent']}%{'+' if b['charging'] else ''}")
            put(1, 1, "battery  " + "   ".join(parts))
        put(3, 1, " " * 8 + "".join(f"{t:^14}" for t in TAPS), curses.A_DIM)
        for r, bud in enumerate(BUDS):
            put(5 + 2 * r, 1, f"{bud:<8}")
            for c, tap in enumerate(TAPS):
                v = self.value(bud, tap)
                cell = "?" if v is None else action_name(v)
                dirty = (bud, tap) in self.pending
                attr = curses.A_REVERSE if (r, c) == (self.row, self.col) else 0
                if dirty:
                    attr |= curses.A_BOLD
                put(5 + 2 * r, 9 + 14 * c, f"{cell + ('*' if dirty else ''):^13}", attr)
        status = ("working: " if self.busy else "error: " if self.err else "") + self.msg
        put(10, 1, status, curses.A_BOLD if self.err else 0)
        put(12, 1, "arrows move  n/p change  w write  u discard  r refresh  R reset  q quit", curses.A_DIM)
        scr.refresh()

    def loop(self):
        curses.curs_set(0)
        self.refresh()
        while True:
            self.draw()
            k = self.scr.getch()
            if k in (ord("q"), 27):
                return
            elif k in (curses.KEY_UP, ord("k")):
                self.row = max(0, self.row - 1)
            elif k in (curses.KEY_DOWN, ord("j")):
                self.row = min(len(BUDS) - 1, self.row + 1)
            elif k in (curses.KEY_LEFT, ord("h")):
                self.col = max(0, self.col - 1)
            elif k in (curses.KEY_RIGHT, ord("l")):
                self.col = min(len(TAPS) - 1, self.col + 1)
            elif k in (ord("n"), ord("+"), ord("]"), ord("p"), ord("-"), ord("[")):
                key = (BUDS[self.row], TAPS[self.col])
                cur = self.value(*key)
                new = cycle(cur, 1 if k in (ord("n"), ord("+"), ord("]")) else -1)
                if new == self.gestures.get(key[0], {}).get(key[1]):
                    self.pending.pop(key, None)
                else:
                    self.pending[key] = new
            elif k == ord("w"):
                self.write()
            elif k == ord("u"):
                self.pending.clear()
                self.msg = "changes discarded"
            elif k == ord("r"):
                self.refresh()
            elif k == ord("R"):
                self.reset()


def main():
    if not sys.stdout.isatty():
        sys.exit("buds_tui needs an interactive terminal")
    curses.wrapper(lambda scr: App(scr).loop())


if __name__ == "__main__":
    main()
