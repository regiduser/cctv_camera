"""Small standard-library tests for the stream framing protocol."""
import socket
import struct
import threading
import unittest

from protocol import ProtocolError, receive_frame, receive_token, send_frame, send_token



class ProtocolTests(unittest.TestCase):
    def test_token_round_trip(self):
        left, right = socket.socketpair()
        try:
            thread = threading.Thread(target=lambda: send_token(left, "secret-token"))
            thread.start()
            self.assertEqual(receive_token(right), "secret-token")
            thread.join()
        finally:
            left.close()
            right.close()


    def test_frame_round_trip(self):
        left, right = socket.socketpair()
        payload = b"jpeg-data"
        try:
            thread = threading.Thread(target=lambda: send_frame(left, payload))
            thread.start()
            self.assertEqual(receive_frame(right), payload)
            thread.join()
        finally:
            left.close()
            right.close()


    def test_oversized_frame_header_rejected(self):
        left, right = socket.socketpair()
        try:
            left.sendall(struct.pack("!I", 4 * 1024 * 1024 + 1))
            with self.assertRaises(ProtocolError):
                receive_frame(right)
        finally:
            left.close()
            right.close()


    def test_empty_frame_rejected_by_sender(self):
        left, right = socket.socketpair()
        try:
            with self.assertRaises(ProtocolError):
                send_frame(left, b"")
        finally:
            left.close()
            right.close()


if __name__ == "__main__":
    unittest.main()
