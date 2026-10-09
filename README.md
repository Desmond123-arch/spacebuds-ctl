# buds

Remap the tap gestures on **Oraimo Spacebuds Neo** earbuds, read their battery, and put both
in your tmux status bar. The buds use a Jieli AC69xx chip; this talks to it over Bluetooth
RFCOMM with Jieli's RCSP protocol, the same one the Oraimo app uses.

I reverse engineered the protocol from a phone's Bluetooth HCI log. See
[docs/protocol.md](docs/protocol.md) for how it works and what is and isn't verified.

## Requirements

- **Windows** with Python 3.9+ (the Bluetooth socket only works there; WSL has no Bluetooth).
  No third-party packages.
- Buds paired with the PC, and **not connected to your phone** (they accept one client at a time).
- For the TUI and tmux battery segment: WSL with `python3` and `tmux`.

## Setup on a new computer

1. **Install Python 3.9+ on Windows** (python.org or the Microsoft Store). Check with `python --version`
   in PowerShell. Nothing else to install.
2. **Get the code** onto the Windows side, for example `git clone <this repo>` into a normal folder
   such as `C:\Users\you\buds`. Keep it on a Windows drive: the TUI and tmux script hand the path to
   Windows Python, which can't run files reliably from inside the WSL filesystem.
3. **Pair the buds with Windows** (Settings, Bluetooth & devices, Add device). Then disconnect them from
   your phone and close the Oraimo app; the buds accept one client at a time.
4. **Find the buds' Bluetooth address.** In PowerShell:

   ```
   Get-PnpDevice -Class Bluetooth | Format-Table FriendlyName, InstanceId
   ```

   The 12 hex digits after `DEV_` in the buds' row are the address, e.g. `24DF17483202` is
   `24:DF:17:48:32:02`. Put it in as the default by editing `DEFAULT_MAC` in `buds.py`, or pass
   `--mac` / set `BUDS_MAC` for one-off use.
5. **Check it works:** `python buds.py status`. You should see battery and a gesture table. If you get a
   connection error, re-check steps 3 and 4. `python buds.py --raw status` prints every frame.
6. **Optional, the TUI and tmux battery (WSL):** needs `python3` and `tmux` in WSL, and `python.exe` on the
   PATH (WSL does this by default). Then:

   ```
   python3 /mnt/c/Users/you/buds/buds_tui.py
   ln -s /mnt/c/Users/you/buds/buds_battery.sh ~/.tmux/plugins/tmux/scripts/buds-battery.sh
   ```

   and add the config from the [tmux](#tmux) section to `~/.tmux.conf`, then press `prefix + r`.
   If you use `BUDS_MAC` instead of editing `DEFAULT_MAC`, forward it into Windows programs:
   `export BUDS_MAC=24:DF:17:48:32:02 WSLENV=$WSLENV:BUDS_MAC`.

**Not on Windows?** The Bluetooth part is plain Python RFCOMM sockets, so on native Linux with BlueZ it should work
too. Pair the buds, then run `python3 buds.py status`, and point the TUI at it with
`BUDS_CMD="python3 /path/to/buds.py"`. I haven't tested that. macOS isn't supported, because Python's `socket`
module has no Bluetooth there.

## Command line

```
python buds.py status                                    # battery and gestures
python buds.py gestures
python buds.py set --single playpause --double next --triple prev
python buds.py set --bud left --double none              # only the slots you name change
python buds.py reset                                     # factory gestures
python buds.py --raw status                              # print every frame, for debugging
python buds.py --json status                             # machine-readable
```

Actions: `none`, `prev`, `next`, `playpause`, or a raw number. Set `BUDS_MAC` or pass `--mac`
if your buds' address isn't `24:DF:17:48:32:02`.

## Terminal UI (from WSL)

```
python3 buds_tui.py
```

Arrows or `hjkl` move, `n`/`p` change the action, `w` writes, `u` discards, `r` refreshes,
`R` resets, `q` quits. Each action calls `python.exe buds.py --json ...` (override with `BUDS_CMD`).

## tmux

Battery in the Dracula status bar, and `prefix + B` to open the TUI:

```
ln -s "$PWD/buds_battery.sh" ~/.tmux/plugins/tmux/scripts/buds-battery.sh
```

```tmux
set -g @dracula-plugins "ram-usage cpu-usage time weather custom:buds-battery.sh"
set -g @dracula-colors "black='#000000'"
set -g @dracula-custom-plugin-colors "black white"
bind B display-popup -E -w 60 -h 16 'python3 "/path/to/buds_tui.py"'
```

The battery script caches for 2 minutes (each read opens a Bluetooth connection), shows
`🎧 --` when the buds are unreachable, and stays quiet while the TUI is open.

## Tests

```
python3 -m unittest discover -s tests
```

Runs against a simulated bud, plus two challenge/response pairs captured from real hardware.

## Caveats

- Verified on one pair of buds (firmware v1.0). Writes only touch the small gesture table, and
  `reset` restores it; nothing here flashes firmware.
- Which bud is `1` vs `2`, and the battery byte layout, are inferred from one capture.
- Function codes 3, 4, 5 and 0 are confirmed. The app also uses 9 and 10; I don't know what they do.

## Credits

Built by Desmond Opoku Mends together with [Claude](https://claude.com/claude-code) (Claude Sonnet 5.5, via Claude Code)

The link-authentication cipher is a port of `jl_auth_2.0.0.js` from Jieli's own
[WeChat-Mini-Program-OTA](https://github.com/Jieli-Tech/WeChat-Mini-Program-OTA) repository.
This project is not affiliated with Oraimo or Jieli.
