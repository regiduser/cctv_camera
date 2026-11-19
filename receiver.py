"""Authenticated CCTV receiver, display, recorder, and optional Telegram uploader."""
from __future__ import annotations
import logging
import hmac
import os
import socket
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import requests
from dotenv import load_dotenv
from protocol import ProtocolError, receive_frame, receive_token

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("cctv.receiver")
HOST = os.getenv("RECEIVER_HOST", "0.0.0.0")
PORT = int(os.getenv("RECEIVER_PORT", "9999"))
SOCKET_TIMEOUT = float(os.getenv("SOCKET_TIMEOUT", "10"))
RECORD_FPS = max(1, int(os.getenv("RECORD_FPS", "20")))
RECORD_DIR = Path(os.getenv("RECORD_DIR", "recordings"))
STREAM_TOKEN = os.getenv("CCTV_STREAM_TOKEN", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_UPLOAD = os.getenv("TELEGRAM_UPLOAD", "false").lower() in {"1", "true", "yes", "on"}



def telegram_upload(video_path: Path) -> bool:
    if not TELEGRAM_UPLOAD:
        log.info("Telegram upload disabled")
        return False
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram upload enabled but credentials are missing")
        return False
    endpoint = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendVideo"
    try:
        with video_path.open("rb") as video:
            response = requests.post(
                endpoint,
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": f"CCTV recording: {video_path.name}"},
                files={"video": video},
                timeout=(10, 120),
            )
        if response.ok:
            log.info("Telegram upload succeeded for %s", video_path.name)
            return True
        log.error("Telegram upload returned HTTP %s: %s", response.status_code, response.text[:500])
    except requests.RequestException:
        log.exception("Telegram upload failed")
    return False



def create_writer(path: Path, frame: np.ndarray) -> cv2.VideoWriter:
    height, width = frame.shape[:2]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), RECORD_FPS, (width, height))
    if not writer.isOpened():
        writer.release()
        raise RuntimeError(f"Could not create recording file: {path}")
    return writer



def receive_client(conn: socket.socket, addr: tuple) -> bool:
    log.info("Connection from %s", addr)
    conn.settimeout(SOCKET_TIMEOUT)
    writer = None
    recording_path = None
    frame_count = 0
    stop_server = False
    try:
        received_token = receive_token(conn)
        if not STREAM_TOKEN or not hmac.compare_digest(received_token, STREAM_TOKEN):
            log.warning("Rejected client %s: authentication failed", addr)
            return
        log.info("Authenticated stream client %s", addr)
        RECORD_DIR.mkdir(parents=True, exist_ok=True)
        while True:
            payload = receive_frame(conn)
            frame = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                log.warning("Invalid JPEG payload from %s; skipping", addr)
                continue
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(frame, stamp, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)
            if writer is None:
                recording_path = RECORD_DIR / f"recording_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.mp4"
                writer = create_writer(recording_path, frame)
                log.info("Recording to %s", recording_path)
            writer.write(frame)
            frame_count += 1
            cv2.imshow("CCTV Receiver (press q to stop)", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                log.info("Local stop requested; shutting down receiver")
                stop_server = True
                break
    except (ConnectionError, OSError, ProtocolError) as exc:
        log.info("Stream ended from %s: %s", addr, exc)
    except Exception:
        log.exception("Unexpected receiver error for %s", addr)
    finally:
        if writer is not None:
            writer.release()
            log.info("Recording finalized (%d frames): %s", frame_count, recording_path)
        try:
            conn.close()
        except OSError:
            pass
        cv2.destroyAllWindows()
        if recording_path and recording_path.exists() and recording_path.stat().st_size > 0:
            telegram_upload(recording_path)
    return stop_server


def main() -> None:
    if not STREAM_TOKEN:
        raise SystemExit("CCTV_STREAM_TOKEN must be configured in .env before starting receiver")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind((HOST, PORT))
        server.listen(3)
        server.settimeout(1.0)
        log.info("Listening on %s:%s", HOST, PORT)
        while True:
            try:
                conn, addr = server.accept()
                if receive_client(conn, addr):
                    break
            except socket.timeout:
                continue
            except KeyboardInterrupt:
                log.info("Receiver interrupted")
                break
            except OSError as exc:
                log.error("Accept failed: %s", exc)
                time.sleep(0.5)
    finally:
        server.close()
        cv2.destroyAllWindows()
        log.info("Receiver stopped")


if __name__ == "__main__":
    main()
