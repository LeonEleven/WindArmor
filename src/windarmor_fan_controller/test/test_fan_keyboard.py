import os
import time
import tty

from windarmor_fan_controller import fan_keyboard


def test_split_arrow_sequence_is_read_as_one_key(monkeypatch) -> None:
    """即使方向键字节跨越多轮主循环，也应组装为一次按键。"""
    master_fd, slave_fd = os.openpty()
    tty.setraw(slave_fd)
    slave_stream = os.fdopen(slave_fd, "r", encoding="utf-8", buffering=1)
    monkeypatch.setattr(fan_keyboard.sys, "stdin", slave_stream)
    reader = fan_keyboard._KeyReader()

    try:
        os.write(master_fd, b"\x1b")
        assert reader.get_key(timeout=0.1) == ""
        time.sleep(0.35)

        os.write(master_fd, b"[")
        assert reader.get_key(timeout=0.1) == ""
        time.sleep(0.35)

        os.write(master_fd, b"A")
        assert reader.get_key(timeout=0.1) == "\x1b[A"
    finally:
        slave_stream.close()
        os.close(master_fd)


def test_buffered_arrow_sequences_are_returned_individually(monkeypatch) -> None:
    """终端一次送来多个重复键时，每轮只处理一次步进。"""
    master_fd, slave_fd = os.openpty()
    tty.setraw(slave_fd)
    slave_stream = os.fdopen(slave_fd, "r", encoding="utf-8", buffering=1)
    monkeypatch.setattr(fan_keyboard.sys, "stdin", slave_stream)
    reader = fan_keyboard._KeyReader()

    try:
        os.write(master_fd, b"\x1b[A\x1b[B")
        assert reader.get_key(timeout=0.1) == "\x1b[A"
        assert reader.get_key(timeout=0.1) == "\x1b[B"
    finally:
        slave_stream.close()
        os.close(master_fd)
