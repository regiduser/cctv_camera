# CCTV Camera - Review Improvements

## Original problems identified
- Sender used `sendall()` as though it returned a byte count (it returns `None`), making the send accounting incorrect.
- Receiver deserialized network-controlled frames with `pickle.loads()`, which is unsafe for untrusted network traffic.
- Stream payload size was not bounded before buffering, exposing the receiver to excessive memory consumption.
- Several settings were hardcoded rather than configurable.
- Reconnection was limited and not resilient to prolonged receiver downtime.
- Telegram upload did not use a request timeout.
- The original dependency list included an unused Telegram package and omitted `requests`, which the code imports.

## Improvements made
- Replaced pickle framing with a length-prefixed raw-JPEG protocol.
- Added a maximum frame size of 4 MiB and exact socket reads.
- Added shared-token authentication before accepting stream frames.
- Used constant-time token comparison.
- Fixed sender frame transmission using `sendall()` without return-value arithmetic.
- Added sender reconnect backoff.
- Added configuration through environment variables and `.env`.
- Added recording directory creation and MP4 recording with release in cleanup.
- Added frame timestamp overlay and local stop key.
- Added optional Telegram upload with connect/read timeout and exception handling.
- Added README, `.env.example`, `.gitignore`, and standard-library protocol tests.

## Verification
- Python bytecode compilation: passed.
- Protocol unit tests: 4 passed.
- Dependencies imported in the current environment: passed.
- End-to-end camera and network test: not run (no paired camera/receiver session).

## Security limitations
The stream token authenticates the sender but the TCP stream is not encrypted. Run only on a trusted network or protect it with a VPN/secure tunnel. Do not expose the receiver port directly to the public internet. This project is a demonstration/student project, not a production security camera platform.

