from enum import Enum, IntEnum
import struct


class Endianness(Enum):
    little = 1
    big = 2

    def struct_code(self):
        return '<' if (self is Endianness.little) else '>'

    def dbus_code(self):
        return b'l' if (self is Endianness.little) else b'B'


endian_map = {b'l': Endianness.little, b'B': Endianness.big}


class MessageType(Enum):
    method_call = 1
    method_return = 2
    error = 3
    signal = 4


msg_type_map = {t.value: t for t in MessageType}

# Flags:
NO_REPLY_EXPECTED = 1
NO_AUTO_START = 2
ALLOW_INTERACTIVE_AUTHORIZATION = 4


class HeaderFields(IntEnum):
    path = 1
    interface = 2
    member = 3
    error_name = 4
    reply_serial = 5
    destination = 6
    sender = 7
    signature = 8
    unix_fds = 9

header_fields_map = {t.value: t for t in HeaderFields}

def padding(pos, step):
    pad = step - (pos % step)
    if pad == step:
        return 0
    return pad


class FixedType:
    def __init__(self, size, struct_code):
        self.size = self.alignment = size
        self.struct_code = struct_code

    def parse_data(self, buf, pos, endianness):
        pos += padding(pos, self.alignment)
        code = endianness.struct_code() + self.struct_code
        val = struct.unpack(code, buf[pos:pos + self.size])[0]
        return val, pos + self.size

    def serialise(self, data, pos, endianness):
        pad = b'\0' * padding(pos, self.alignment)
        code = endianness.struct_code() + self.struct_code
        return pad + struct.pack(code, data)

    def __repr__(self):
        return 'FixedType({!r}, {!r})'.format(self.size, self.struct_code)


simple_types = {
    'y': FixedType(1, 'B'),  # unsigned 8 bit
    'b': FixedType(4, 'I'),  # bool
    'n': FixedType(2, 'h'),  # signed 16 bit
    'q': FixedType(2, 'H'),  # unsigned 16 bit
    'i': FixedType(4, 'i'),  # signed 32-bit
    'u': FixedType(4, 'I'),  # unsigned 32-bit
    'x': FixedType(8, 'q'),  # signed 64-bit
    't': FixedType(8, 'Q'),  # unsigned 64-bit
    'd': FixedType(8, 'd'),  # double
    'h': FixedType(8, 'I'),  # file descriptor (32-bit unsigned, index)
}


class StringType:
    def __init__(self, length_type):
        self.length_type = length_type

    @property
    def alignment(self):
        return self.length_type.size

    def parse_data(self, buf, pos, endianness):
        length, pos = self.length_type.parse_data(buf, pos, endianness)
        end = pos + length
        val = buf[pos:end].decode('utf-8')
        assert buf[end:end + 1] == b'\0'
        return val, end + 1

    def serialise(self, data, pos, endianness):
        encoded = data.encode('utf-8')
        len_data = self.length_type.serialise(len(encoded), pos, endianness)
        return len_data + encoded + b'\0'


simple_types.update({
    's': StringType(simple_types['u']),  # String
    'o': StringType(simple_types['u']),  # Object path
    'g': StringType(simple_types['y']),  # Signature
})


class Struct:
    alignment = 8

    def __init__(self, fields):
        if any(isinstance(f, DictEntry) for f in fields):
            raise TypeError("Found dict entry outside array")
        self.fields = fields

    def parse_data(self, buf, pos, endianness):
        pos += padding(pos, 8)
        res = []
        for field in self.fields:
            v, pos = field.parse_data(buf, pos, endianness)
            res.append(v)
        return tuple(res), pos

    def serialise(self, data, pos, endianness):
        if len(data) != len(self.fields):
            raise ValueError("{} entries for {} fields".format(
                len(data), len(self.fields)
            ))
        pad = b'\0' * padding(pos, self.alignment)
        pos += len(pad)
        res_pieces = []
        for item, field in zip(data, self.fields):
            res_pieces.append(field.serialise(item, pos, endianness))
            pos += len(res_pieces[-1])
        return pad + b''.join(res_pieces)

    def __repr__(self):
        return "{}({!r})".format(type(self).__name__, self.fields)


class DictEntry(Struct):
    def __init__(self, fields):
        if len(fields) != 2:
            raise TypeError(
                "Dict entry must have 2 fields, not %d" % len(fields))
        if not isinstance(fields[0], (FixedType, StringType)):
            raise TypeError(
                "First field in dict entry must be simple type, not {}"
                .format(type(fields[0])))
        super().__init__(fields)


class Array:
    alignment = 4
    length_type = FixedType(4, 'I')

    def __init__(self, elt_type):
        self.elt_type = elt_type

    def parse_data(self, buf, pos, endianness):
        # print('Array start', pos)
        length, pos = self.length_type.parse_data(buf, pos, endianness)
        pos += padding(pos, self.elt_type.alignment)
        end = pos + length
        res = []
        while pos < end:
            # print('Array elem', pos)
            v, pos = self.elt_type.parse_data(buf, pos, endianness)
            res.append(v)
        return res, pos

    def serialise(self, data, pos, endianness):
        pad1 = padding(pos, self.alignment)
        pos_after_length = pos + pad1 + 4
        pad2 = padding(pos_after_length, self.elt_type.alignment)
        data_pos = pos_after_length + pad2
        chunks = []
        for item in data:
            chunks.append(self.elt_type.serialise(item, data_pos, endianness))
            data_pos += len(chunks[-1])
        buf = b''.join(chunks)
        len_data = self.length_type.serialise(len(buf), pos, endianness)
        pos += len(len_data)
        pad = b'\0' * padding(pos, self.elt_type.alignment)
        return (b'\0' * pad1) + len_data + (b'\0' * pad2) + buf

    def __repr__(self):
        return 'Array({!r})'.format(self.elt_type)


class Variant:
    alignment = 1

    def parse_data(self, buf, pos, endianness):
        # print('variant', pos)
        sig, pos = simple_types['g'].parse_data(buf, pos, endianness)
        # print('variant sig:', repr(sig), pos)
        valtype = parse_signature(list(sig))
        val, pos = valtype.parse_data(buf, pos, endianness)
        # print('variant done', (sig, val), pos)
        return (sig, val), pos

    def serialise(self, data, pos, endianness):
        sig, data = data
        valtype = parse_signature(list(sig))
        sig_buf = simple_types['g'].serialise(sig, pos, endianness)
        return sig_buf + valtype.serialise(data, pos + len(sig_buf), endianness)

    def __repr__(self):
        return 'Variant()'


def parse_signature(sig):
    # Based on http://norvig.com/lispy.html
    token = sig.pop(0)
    if token == 'a':
        return Array(parse_signature(sig))
    if token == 'v':
        return Variant()
    elif token == '(':
        fields = []
        while sig[0] != ')':
            fields.append(parse_signature(sig))
        sig.pop(0)  # )
        return Struct(fields)
    elif token == '{':
        de = []
        while sig[0] != '}':
            de.append(parse_signature(sig))
        sig.pop(0)  # }
        return DictEntry(de)
    elif token in ')}':
        raise ValueError('Unexpected end of struct')
    else:
        return simple_types[token]


def calc_msg_size(buf):
    endian, = struct.unpack('c', buf[:1])
    endian = endian_map[endian]
    body_length, = struct.unpack(endian.struct_code() + 'I', buf[4:8])
    fields_array_len, = struct.unpack(endian.struct_code() + 'I', buf[12:16])
    header_len = 16 + fields_array_len
    return header_len + padding(header_len, 8) + body_length


_header_fields_type = Array(Struct([simple_types['y'], Variant()]))


def parse_header_fields(buf, endianness):
    l, pos = _header_fields_type.parse_data(buf, 12, endianness)
    return {header_fields_map[k]: v[1] for (k, v) in l}, pos


header_field_codes = {
    1: 'o',
    2: 's',
    3: 's',
    4: 's',
    5: 'u',
    6: 's',
    7: 's',
    8: 'g',
    9: 'u',
}


def serialise_header_fields(d, endianness):
    l = [(i.value, (header_field_codes[i], v)) for (i, v) in sorted(d.items())]
    return _header_fields_type.serialise(l, 12, endianness)


class Header:
    def __init__(self, endianness, message_type, flags, protocol_version,
                 body_length, serial, fields):
        self.endianness = endianness
        self.message_type = message_type
        self.flags = flags
        self.protocol_version = protocol_version
        self.body_length = body_length
        self.serial = serial
        self.fields = fields

    def __repr__(self):
        return 'Header({!r}, {!r}, {!r}, {!r}, {!r}, {!r}, fields={!r})'.format(
            self.endianness, self.message_type, self.flags,
            self.protocol_version, self.body_length, self.serial, self.fields)

    def serialise(self):
        s = self.endianness.struct_code() + 'cBBBII'
        return struct.pack(s, self.endianness.dbus_code(),
                           self.message_type.value, self.flags,
                           self.protocol_version,
                           self.body_length, self.serial) \
                + serialise_header_fields(self.fields, self.endianness)

    @classmethod
    def from_buffer(cls, buf):
        endian, msgtype, flags, pv = struct.unpack('cBBB', buf[:4])
        endian = endian_map[endian]
        bodylen, serial = struct.unpack(endian.struct_code() + 'II', buf[4:12])
        fields, pos = parse_header_fields(buf, endian)
        return cls(endian, msg_type_map[msgtype], flags, pv, bodylen,
                   serial, fields), pos


class Message:
    def __init__(self, header, body):
        self.header = header
        self.body = body

    def __repr__(self):
        return "{}({!r}, {!r})".format(type(self).__name__, self.header, self.body)

    @classmethod
    def from_buffer(cls, buf):
        header, pos = Header.from_buffer(buf)
        body = ()
        if HeaderFields.signature in header.fields:
            sig = header.fields[HeaderFields.signature]
            body_type = parse_signature(list('(%s)' % sig))
            body = body_type.parse_data(buf, pos, header.endianness)[0]
        return cls(header, body)

    def serialise(self):
        header_buf = self.header.serialise()
        pos = len(header_buf)
        endian = self.header.endianness

        if HeaderFields.signature in self.header.fields:
            sig = self.header.fields[HeaderFields.signature]
            body_type = parse_signature(list('(%s)' % sig))
            body_buf = body_type.serialise(self.body, pos, endian)
        else:
            body_buf = b'\0' * padding(pos, 8)

        return header_buf + body_buf


class Parser:
    def __init__(self):
        self.buf = b''
        self.fixed_header = None
        self.next_msg_size = None

    def feed(self, data):
        self.buf += data
        return list(iter(self._read1, None))

    def _read1(self):
        if self.next_msg_size is None:
            if len(self.buf) >= 16:
                self.next_msg_size = calc_msg_size(self.buf)
        nms = self.next_msg_size
        if (nms is not None) and len(self.buf) >= nms:
            raw_msg, self.buf = self.buf[:nms], self.buf[nms:]
            msg = Message.from_buffer(raw_msg)
            self.next_msg_size = None
            return msg
