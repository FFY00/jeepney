from jeepney.low_level import *

HELLO_METHOD_CALL = (
    b'l\x01\x00\x01\x00\x00\x00\x00\x01\x00\x00\x00m\x00\x00\x00\x01\x01o\x00\x15'
    b'\x00\x00\x00/org/freedesktop/DBus\x00\x00\x00\x02\x01s\x00\x14\x00\x00\x00'
    b'org.freedesktop.DBus\x00\x00\x00\x00\x03\x01s\x00\x05\x00\x00\x00Hello\x00'
    b'\x00\x00\x06\x01s\x00\x14\x00\x00\x00org.freedesktop.DBus\x00\x00\x00\x00')


def test_parser_simple():
    msg = Parser().feed(HELLO_METHOD_CALL)[0]
    assert msg.header.fields[HeaderFields.member] == 'Hello'

def chunks(src, size):
    pos = 0
    while pos < len(src):
        end = pos + size
        yield src[pos:end]
        pos = end

def test_parser_chunks():
    p = Parser()
    chunked = list(chunks(HELLO_METHOD_CALL, 16))
    for c in chunked[:-1]:
        assert p.feed(c) == []
    msg = p.feed(chunked[-1])[0]
    assert msg.header.fields[HeaderFields.member] == 'Hello'

def test_multiple():
    msgs = Parser().feed(HELLO_METHOD_CALL * 6)
    assert len(msgs) == 6
    for msg in msgs:
        assert msg.header.fields[HeaderFields.member] == 'Hello'

def test_roundtrip():
    msg = Parser().feed(HELLO_METHOD_CALL)[0]
    assert msg.serialise() == HELLO_METHOD_CALL

def test_serialise_dict():
    data = {
        'a': 'b',
        'de': 'f',
    }
    string_type = simple_types['s']
    sig = Array(DictEntry([string_type, string_type]))
    print(sig.serialise(data, 0, Endianness.little))
    assert sig.serialise(data, 0, Endianness.little) == (
        b'\x1e\0\0\0' +  # Length
        b'\0\0\0\0' +  # Padding
        b'\x01\0\0\0a\0\0\0' +
        b'\x01\0\0\0b\0\0\0' +
        b'\x02\0\0\0de\0\0' +
        b'\x01\0\0\0f\0'
    )
