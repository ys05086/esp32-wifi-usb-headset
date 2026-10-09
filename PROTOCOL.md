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

Listening level: `<4sIhHI`, 16 bytes: magic VSL1, the current session, level (Int16, 1/256 dB; -32768 for silence), 0,
command id (UInt32). Taken only from the streaming client for its session. The board ignores a repeat of the last id it
took, so start each connection from a random id and resend the latest command until the board reports it.

## Board to client

Audio: same header with magic VSR1, matching session, a separate sequence counter, frames 480, flags 0, then 960 PCM bytes.
The board averages stereo USB speaker channels into mono. It never mixes them into the USB microphone stream.
It applies the listening level first: the phone's volume for the USB speaker (an iPhone sends the stream at full scale and
sets that volume on the device), or the client's VSL1 level when the client changed it last. The side that changes it
last wins; a phone volume change takes it back. At -50 dB or below it is silence.

Level: with each ACK, `<4shHII`, 16 bytes: magic VSV1, level (Int16, 1/256 dB; -32768 for silence), flags (1: set by
the client, 2: the phone sets a volume), changes (UInt32, from either side), the client's last command id it took.
Clients that do not know VSV1 can drop it.

ACK: `<4sIIIII`, magic VSA2, total mic packets received, USB mic underruns, queued mic frames, return packets sent, return packets dropped.
The PC buffers 40 ms before playback and drops stale queued audio after 300 ms without packets.
Only a stopped/expired owner can be replaced by another endpoint. Use headphones to prevent acoustic feedback.
