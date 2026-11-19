"""Capture camera frames and send JPEG frames to the CCTV receiver."""
from __future__ import annotations
import logging
import os
import socket
import time
from typing import Optional


import cv2
from dotenv import load_dotenv
from protocol import ProtocolError, send_frame, send_token


load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("cctv.sender")
HOST = os.getenv("RECEIVER_HOST", "127.0.0.1")
PORT = int(os.getenv("RECEIVER_PORT", "9999"))
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))
WIDTH = int(os.getenv("FRAME_WIDTH", "640"))
HEIGHT = int(os.getenv("FRAME_HEIGHT", "480"))
FPS = max(1, int(os.getenv("CAMERA_FPS", "20")))
JPEG_QUALITY = min(100, max(1, int(os.getenv("JPEG_QUALITY", "65"))))
SOCKET_TIMEOUT = float(os.getenv("SOCKET_TIMEOUT", "10"))
RECONNECT_DELAY = max(0.25, float(os.getenv("RECONNECT_DELAY", "2")))
STREAM_TOKEN = os.getenv("CCTV_STREAM_TOKEN", "")



def open_camera() -> Optional[cv2.VideoCapture]:
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        cap.release()
        log.error("Could not open camera index %s", CAMERA_INDEX)
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    return cap



def connect() -> socket.socket:
    client = socket.create_connection((HOST, PORT), timeout=SOCKET_TIMEOUT)
    try:
        client.settimeout(SOCKET_TIMEOUT)
        send_token(client, STREAM_TOKEN)
        log.info("Connected to receiver %s:%s", HOST, PORT)
        return client
    except Exception:
        client.close()
        raise



def main() -> None:
    if not STREAM_TOKEN:
        raise SystemExit("CCTV_STREAM_TOKEN must be configured in .env before starting sender")
    cap = open_camera()
    if cap is None:
        raise SystemExit("Camera initialization failed")
    client: Optional[socket.socket] = None
    frame_count = 0
    retry_delay = RECONNECT_DELAY
    frame_interval = 1.0 / FPS
    next_frame_at = time.monotonic()
    try:
        log.info("Streaming camera %s at requested %sx%s", CAMERA_INDEX, WIDTH, HEIGHT)
        while True:
            if client is None:
                try:
                    client = connect()
                    retry_delay = RECONNECT_DELAY
                except (OSError, ProtocolError) as exc:
                    log.warning("Receiver unavailable: %s. Retrying in %.1fs", exc, retry_delay)
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, 30.0)
                    continue
            now = time.monotonic()
            if now < next_frame_at:
                time.sleep(next_frame_at - now)
            next_frame_at = time.monotonic() + frame_interval
            ok, frame = cap.read()
            if not ok or frame is None:
                log.warning("Camera frame unavailable; retrying capture")
                time.sleep(0.1)
                continue
            if frame.shape[1] != WIDTH or frame.shape[0] != HEIGHT:
                frame = cv2.resize(frame, (WIDTH, HEIGHT), interpolation=cv2.INTER_AREA)
            encoded, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if not encoded:
                log.warning("JPEG encoding failed; frame skipped")
                continue
            try:
                send_frame(client, buffer.tobytes())
                frame_count += 1
                if frame_count % (FPS * 30) == 0:
                    log.info("Frames sent: %d", frame_count)
            except (OSError, ProtocolError) as exc:
                log.warning("Stream connection lost: %s", exc)
                try:
                    client.close()
                except OSError:
                    pass
                client = None
    except KeyboardInterrupt:
        log.info("Sender interrupted; shutting down")
    finally:
        if client is not None:
            try:
                client.close()
            except OSError:
                pass
        cap.release()
        log.info("Camera released; sender stopped")


if __name__ == "__main__":
    main()
