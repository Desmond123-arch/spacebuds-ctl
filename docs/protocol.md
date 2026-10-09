# Protocol notes

How these buds talk, as reconstructed from an Android HCI snoop log. Everything below is from
one capture of one pair of Spacebuds Neo (firmware v1.0) unless marked otherwise.

## Transport

Classic Bluetooth. Over L2CAP the phone opens SDP (PSM 0x1), RFCOMM (0x3), AVDTP/A2DP (0x19)
and AVCTP/AVRCP (0x17). RFCOMM carries two services:

| RFCOMM channel | Service |
|---|---|
| 4 | standard Hands-Free (AT commands) |
| 1 | Jieli RCSP, the app's configuration channel |

The chip is a Jieli AC69xx; the capture contains the string `jl_sdk_ac697_publish`.
The gesture "double tap = pause" reaches the phone as a plain AVRCP pass-through command
(`0x46` pause, `0x44` play), so the host only ever sees the final command.

## Authentication

RCSP frames are ignored until a mutual challenge/response succeeds. All messages are sent raw on
the RFCOMM channel:

```
host -> bud   00 <16 random bytes>
bud  -> host  01 <16 bytes>        = respond(challenge)
host -> bud   02 'p' 'a' 's' 's'
bud  -> host  00 <16 random bytes>
host -> bud   01 <16 bytes>        = respond(challenge)
bud  -> host  02 'p' 'a' 's' 's'
```

`respond` is Jieli's published cipher (`jl_auth_2.0.0.js` in
[Jieli-Tech/WeChat-Mini-Program-OTA](https://github.com/Jieli-Tech/WeChat-Mini-Program-OTA)),
ported in `jl_auth.py`. The port reproduces both pairs from the capture and matches the
JavaScript on random inputs (`tests/test_buds.py`).

## RCSP frames

```
FE DC BA | flag | opcode | length (2 bytes, big endian) | body | EF
```

| flag | meaning |
|---|---|
| `C0` | command from the host that wants a reply |
| `00` | reply |
| `80` | notification from the bud |

A command body is `sn payload...` (a one-byte sequence number). A reply body is
`status sn payload...`. There is no checksum.

Opcodes used here (names are mine):

| Opcode | Use |
|---|---|
| `03` | get target info; the app always sends this first |
| `C1` | read the attribute table (payload `ff ff ff ff`) |
| `C0` | write attributes |

## Attribute table

The `C1` reply payload is a list of `len type value...` records, where `len` counts the type byte.

| Type | Meaning |
|---|---|
| `00` | battery: 3 bytes, seen as `64 64 00`. Read as left, right, case; top bit = charging (inferred) |
| `02` | key settings: 6 triples of `bud tap function` |

Key settings:

- `bud`: 1 or 2 (left/right assignment inferred)
- `tap`: 1 single, 2 double, 3 triple
- `function`: 0 none, 3 previous, 4 next, 5 play/pause (confirmed by use); 9 and 10 appear in the
  app's choices but are unidentified

A write is opcode `C0` with body `sn 13 02 <18 bytes>`: the same type-`02` record with all six triples.

## Not explored

Attribute types `03`, `05`, `07`, `0a`, the `07`/`08` system-info opcodes, EQ, and firmware (OTA).
The voice prompts ("connected"/"disconnected") live in the firmware image; nothing in the
capture touches them.
