import os
import select

from bspec import review


def test_read_key_translates_keys_and_escape_sequences():
    """A cbreak terminal delivers arrows as multi-byte escape sequences that arrive
    one byte at a time; _read_key must reassemble them and lowercase plain keys."""
    r, w = os.pipe()
    cases = [
        (b"\x1b[A", "up"), (b"\x1b[B", "down"), (b"\x1b[C", "right"), (b"\x1b[D", "left"),
        (b"\x1bOA", "up"), (b"\x1bOD", "left"),   # SS3 form (application cursor mode)
        (b"c", "c"), (b"Q", "q"), (b"\r", "enter"), (b"\n", "enter"),
        (b"\x1b", "esc"),                         # lone Esc resolves after the deadline
    ]
    for raw, want in cases:
        os.write(w, raw)
        assert review._read_key(r) == want, f"{raw!r} -> want {want!r}"
    os.close(w)
    assert review._read_key(r) == "eof"
    os.close(r)


def test_read_key_consumes_unhandled_sequences_whole():
    """An unhandled CSI sequence (here Ctrl+Up) must be swallowed entirely and ignored —
    if its bytes leaked back, the trailing 'A' would read as 'a' (= approve)."""
    r, w = os.pipe()
    os.write(w, b"\x1b[1;2A")
    assert review._read_key(r) == ""
    assert not select.select([r], [], [], 0.05)[0]  # nothing left in the buffer
    os.close(w)
    os.close(r)
