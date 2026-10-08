# ESP32 duplex-v1

Trusted LAN UDP, port 49152. Each direction carries 48 kHz mono signed PCM16LE.
One active client, identified by source IP/port and nonzero random UInt32 session.
This is not an encrypted Internet transport.

## Client to board

Header: little endian `<4sIIHH`, followed by 960 PCM bytes (480 frames / 10 ms).

| Field | Value |
|---|---|
| Magic | VSM1 |
| Session | Nonzero UInt32 |
| Sequence | Wrapping UInt32 |
| Frames | 480 |
| Flags | 2 (duplex) |

Stop: same header with frames 0 and flags 1, no PCM payload. No audio for 300 ms expires the lease and clears queued speech.

## Board to client

Audio: same header with magic VSR1, matching session, a separate sequence counter, frames 480, flags 0, then 960 PCM bytes.
The board averages stereo USB speaker channels into mono. It never mixes them into the USB microphone stream.

ACK: `<4sIIIII`, magic VSA2, total mic packets received, USB mic underruns, queued mic frames, return packets sent, return packets dropped.
The PC buffers 40 ms before playback and drops stale queued audio after 300 ms without packets.
Only a stopped/expired owner can be replaced by another endpoint. Use headphones to prevent acoustic feedback.
