"""Authenticated CCTV receiver, display, recorder, and optional Telegram uploader."""
from __future__ import annotations
import logging
import hmac
import os
import socket
import time
from collections import deque
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
MOTION_DETECTION = os.getenv("MOTION_DETECTION", "true").lower() in {"1", "true", "yes", "on"}
MOTION_THRESHOLD = max(1, int(os.getenv("MOTION_THRESHOLD", "25")))
MOTION_MIN_AREA = max(100, int(os.getenv("MOTION_MIN_AREA", "1200")))
SHOW_PREVIEW = os.getenv("SHOW_PREVIEW", "true").lower() in {"1", "true", "yes", "on"}



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
    previous_gray = None
    motion_until = 0.0
    frame_times = deque(maxlen=30)
    session_started = time.monotonic()
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

            # Lightweight frame-difference motion detection; no frames leave this receiver.
            motion_detected = False
            if MOTION_DETECTION:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (21, 21), 0)
                if previous_gray is not None:
                    delta = cv2.absdiff(previous_gray, gray)
                    _, mask = cv2.threshold(delta, MOTION_THRESHOLD, 255, cv2.THRESH_BINARY)
                    mask = cv2.dilate(mask, None, iterations=2)
                    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    for contour in contours:
                        if cv2.contourArea(contour) >= MOTION_MIN_AREA:
                            x, y, w, h = cv2.boundingRect(contour)
                            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 180, 255), 2)
                            motion_detected = True
                previous_gray = gray
                if motion_detected:
                    motion_until = time.monotonic() + 2.0

            now = time.monotonic()
            frame_times.append(now)
            live_fps = (len(frame_times) - 1) / max(frame_times[-1] - frame_times[0], 1e-6) if len(frame_times) > 1 else 0.0
            elapsed = int(now - session_started)
            status_color = (0, 180, 255) if now < motion_until else (70, 220, 100)
            cv2.rectangle(frame, (0, 0), (frame.shape[1], 76), (20, 25, 30), -1)
            cv2.putText(frame, "CCTV LIVE  |  RECORDING", (12, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
            status = "MOTION DETECTED" if now < motion_until else ("MOTION MONITORING" if MOTION_DETECTION else "MOTION DETECTION OFF")
            cv2.putText(frame, status, (12, 51), cv2.FONT_HERSHEY_SIMPLEX, 0.48, status_color, 1, cv2.LINE_AA)
            cv2.putText(frame, f"{stamp}  |  {live_fps:.1f} FPS  |  {elapsed // 60:02d}:{elapsed % 60:02d}", (12, frame.shape[0] - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
            if writer is None:
                recording_path = RECORD_DIR / f"recording_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.mp4"
                writer = create_writer(recording_path, frame)
                log.info("Recording to %s", recording_path)
            writer.write(frame)
            frame_count += 1
            if SHOW_PREVIEW:
                cv2.imshow("CCTV Monitor - press q to stop", frame)
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
    if not STREAM_TOKEN or STREAM_TOKEN == "replace-with-a-long-random-token":
        raise SystemExit("Set a unique CCTV_STREAM_TOKEN in .env before starting receiver")
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
