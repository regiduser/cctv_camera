# CCTV Camera Stream

A polished, lightweight Python webcam-to-receiver streaming tool. The sender captures camera frames, encodes them as JPEG, and transmits them over TCP. The receiver authenticates the sender with a shared token, displays frames, records MP4 video, and can optionally upload finished recordings to Telegram.


## Features

- JPEG video streaming over TCP
- Shared-token authentication before frames are accepted
- Bounded frame sizes and safe binary framing (no network `pickle`)
- Sender reconnects with backoff when the receiver is unavailable
- Receiver timestamps frames and records MP4 files
- Optional Telegram upload with request timeouts
- Environment-based configuration; secrets are kept out of source code


## Requirements

- Python 3.10+
- Webcam on the sender computer
- Display/GUI support on the receiver (OpenCV window)
- Network connectivity between sender and receiver


## Setup

1. Clone/download this project on both the sender and receiver computers.
2. Create a virtual environment and install dependencies:


   ```bash
   python -m venv .venv
   ```

   Activate it:

   - Windows PowerShell: ` .\.venv\Scripts\Activate.ps1 `
   - Linux/macOS: `source .venv/bin/activate`

   Then run:

   ```powershell
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```
   **Important:** run the install command from the project folder that contains `requirements.txt`. If PowerShell says the file cannot be found, run `dir` and `Get-ChildItem -Recurse -Filter requirements.txt` to locate it, then `cd` into that folder.
3. Copy `.env.example` to `.env` on each computer. On Windows PowerShell, use `Copy-Item .env.example .env`.
4. Generate a long random stream token and set the same `CCTV_STREAM_TOKEN` value in both `.env` files. For example, Python can generate one using `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
5. On the receiver's `.env`, set `RECEIVER_HOST=0.0.0.0` to listen on network interfaces. Keep the port consistent on both machines. The sender's `RECEIVER_HOST` must be the receiver computer's LAN IP address (not `127.0.0.1` unless they are on the same computer).
6. If streaming across computers, restrict the receiver port in the firewall to trusted devices/network only.


## Run

Start the receiver first:


```bash
python receiver.py
```

Then on the sender computer:


```bash
python sender.py
```

Press **q** in the receiver window to stop the current recording/session. Press `Ctrl+C` in a terminal to stop either process.


## Configuration

| Variable | Default | Description |
|---|---:|---|
| `CCTV_STREAM_TOKEN` | required | Shared authentication token on both ends |
| `RECEIVER_HOST` | sender: `127.0.0.1`; receiver: `0.0.0.0` | Receiver address/listen interface |
| `RECEIVER_PORT` | `9999` | TCP port |
| `SOCKET_TIMEOUT` | `10` | Socket inactivity timeout in seconds |
| `CAMERA_INDEX` | `0` | Sender webcam index |
| `FRAME_WIDTH` | `640` | Capture/stream width |
| `FRAME_HEIGHT` | `480` | Capture/stream height |
| `CAMERA_FPS` | `20` | Requested camera frame rate |
| `JPEG_QUALITY` | `65` | JPEG quality from 1–100 |
| `RECONNECT_DELAY` | `2` | Initial reconnect delay in seconds |
| `RECORD_FPS` | `20` | Recording output FPS |
| `RECORD_DIR` | `recordings` | Directory for recordings on receiver |
| `TELEGRAM_UPLOAD` | `false` | Enable Telegram video upload |
| `TELEGRAM_BOT_TOKEN` | empty | Telegram bot token (receiver only) |
| `TELEGRAM_CHAT_ID` | empty | Telegram destination (receiver only) |
| `LOG_LEVEL` | `INFO` | Python logging level |


## Motion detection and live preview

The receiver enables lightweight motion highlighting by default. It compares consecutive blurred grayscale frames and draws boxes around larger changes. It is a simple demo feature, not a reliable alarm system; lighting changes and camera shake can trigger it, and small/distant motion can be missed.

Tune these receiver-side settings in `.env`:
- `MOTION_DETECTION=true` enables/disables motion highlighting.
- `MOTION_THRESHOLD=25` controls pixel-change sensitivity (lower is more sensitive).
- `MOTION_MIN_AREA=1200` controls the minimum contour size.
- `SHOW_PREVIEW=true` shows the OpenCV preview; set `false` for headless recording (a desktop is still recommended for testing).

## Telegram upload

Telegram upload is disabled by default. To enable it, set `TELEGRAM_UPLOAD=true`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID` in the receiver's local `.env`. Never commit `.env` or share bot tokens.


## Protocol and security notes

The stream protocol uses a 2-byte token length, token bytes, then repeated 4-byte network-order frame lengths and raw JPEG payloads. Payloads are capped at 4 MiB. This replaces unsafe `pickle` deserialization.

The shared token authenticates peers but **does not encrypt the video stream**. Use only on a trusted LAN or protect the connection with a VPN/secure tunnel. Do not expose the receiver port directly to the public internet. A token is not a replacement for TLS.


## Troubleshooting

- **Camera not found:** check camera permissions, close other camera applications, or try another `CAMERA_INDEX`.
- **Sender cannot connect:** verify receiver is running, host/port match, and firewall allows the port on the trusted network.
- **Authentication rejected:** verify the token is identical on both machines and has no accidental whitespace.
- **Recording cannot be opened:** install OpenCV's standard package and check write permissions for `RECORD_DIR`.
- **Telegram upload fails:** check upload is enabled, credentials are correct, internet access exists, and the video is within Telegram limits.


## Limitations

- The receiver handles one sender at a time.
- The recording is finalized when the sender disconnects or the receiver stops the session.
- The receiver uses OpenCV GUI functions and needs a desktop display session.
- This is a student/demo project, not a hardened production surveillance system. For deployment, add TLS, stronger device identity, access controls, storage retention policy, privacy safeguards, and monitoring.
