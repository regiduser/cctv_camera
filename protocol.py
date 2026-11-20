"""Safe, bounded TCP framing for CCTV JPEG frames (no pickle)."""
from __future__ import annotations
import socket
import struct

FRAME_HEADER = struct.Struct("!I")
TOKEN_HEADER = struct.Struct("!H")
MAX_FRAME_BYTES = 4 * 1024 * 1024
MAX_TOKEN_BYTES = 4096


class ProtocolError(Exception):
    """Raised when a peer sends malformed or oversized protocol data."""


def recv_exact(sock: socket.socket, size: int) -> bytes:
    if size < 0:
        raise ProtocolError("Negative payload size")
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(min(65536, size - len(data)))
        if not chunk:
            raise ConnectionError("Peer disconnected during payload transfer")
        data.extend(chunk)
    return bytes(data)


def send_token(sock: socket.socket, token: str) -> None:
    encoded = token.encode("utf-8")
    if len(encoded) > MAX_TOKEN_BYTES:
        raise ProtocolError("Token exceeds protocol limit")
    sock.sendall(TOKEN_HEADER.pack(len(encoded)) + encoded)


def receive_token(sock: socket.socket) -> str:
    length = TOKEN_HEADER.unpack(recv_exact(sock, TOKEN_HEADER.size))[0]
    if length > MAX_TOKEN_BYTES:
        raise ProtocolError("Token exceeds protocol limit")
    return recv_exact(sock, length).decode("utf-8")



def send_frame(sock: socket.socket, jpeg_bytes: bytes) -> None:
    if not jpeg_bytes or len(jpeg_bytes) > MAX_FRAME_BYTES:
        raise ProtocolError("Invalid or oversized frame")
    sock.sendall(FRAME_HEADER.pack(len(jpeg_bytes)) + jpeg_bytes)


def receive_frame(sock: socket.socket) -> bytes:
    length = FRAME_HEADER.unpack(recv_exact(sock, FRAME_HEADER.size))[0]
    if length == 0 or length > MAX_FRAME_BYTES:
        raise ProtocolError(f"Invalid frame size: {length}")
    return recv_exact(sock, length)
