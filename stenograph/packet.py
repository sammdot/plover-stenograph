from enum import IntEnum
from struct import Struct, calcsize, pack, unpack
from more_itertools import grouper
from itertools import compress

from stenograph.stroke import Stroke

MAX_READ = 0x200  # Arbitrary read limit


class PacketType(IntEnum):
    ERROR = 0x6
    OPEN_FILE = 0x11
    READ_FILE = 0x13


class ErrorType(IntEnum):
    UNABLE_TO_PERFORM = 3
    FILE_NOT_AVAILABLE = 7
    NO_REALTIME_FILE = 8
    FINISHED_READING_CLOSED_FILE = 9


class StenoPacket:
    """
    Stenograph StenoPacket helper

    Can be used to create packets to send to the writer, as well as
    decode a packet from the writer.
    """
    _SYNC = b'SG'

    """
    Packet header format:
    'SG'     sequence number  packet ID  data length p1,p2,p3,p4,p5
    2 chars  4 bytes          2 bytes    4 bytes     4 bytes each
    """
    _STRUCT_FORMAT = '<2sIH6I'
    HEADER_SIZE = calcsize(_STRUCT_FORMAT)
    _STRUCT = Struct(_STRUCT_FORMAT)


    sequence_number = 0

    def __init__(self, sequence_number=None, packet_type=0, data_length=None,
                 p1=0, p2=0, p3=0, p4=0, p5=0, data=b''):
        """Create a USB Packet

        sequence_number -- ideally unique, if not passed one will be assigned sequentially.

        packet_type -- type of packet.

        data_length -- length of the additional data, calculated if not provided.

        p1, p2, p3, p4, p5 -- 4 byte parameters that have different roles based on packet_type

        data -- data to be appended to the end of the packet, used for steno strokes from the writer.
        """
        if sequence_number is None:
            sequence_number = StenoPacket.sequence_number
            StenoPacket._increment_sequence_number()
        if data is not None:
            # Data is padded to 8 bytes
            remainder = len(data) % 8
            if remainder:
                data += b'\x00' * (8 - remainder)
        if data_length is None:
            data_length = len(data)
        self.sequence_number = sequence_number
        self.packet_type = PacketType(packet_type)
        self.data_length = data_length
        self.p1 = p1
        self.p2 = p2
        self.p3 = p3
        self.p4 = p4
        self.p5 = p5
        self.data = data

    def __str__(self):
        return (
            'StenoPacket(sequence_number=%s, '
            'packet_type=%s(%s), data_length=%s, '
            'p1=%s, p2=%s, p3=%s, p4=%s, p5=%s, data=%s)'
            % (hex(self.sequence_number), hex(self.packet_type), self.packet_type.name,
               self.data_length, hex(self.p1), hex(self.p2),
               hex(self.p3), hex(self.p4), hex(self.p5),
               self.data[:self.data_length])
        )

    def pack(self):
        """Convert this USB Packet into something that can be sent to the writer."""
        return self._STRUCT.pack(
            self._SYNC, self.sequence_number, self.packet_type, self.data_length,
            self.p1, self.p2, self.p3, self.p4, self.p5
        ) + (
            pack('%ss' % len(self.data), self.data)
        )

    @staticmethod
    def _increment_sequence_number():
        StenoPacket.sequence_number = (StenoPacket.sequence_number + 1) % 0xFFFFFFFF

    @staticmethod
    def unpack(usb_packet):
        """Create a USBPacket from raw data"""
        packet = StenoPacket(
            # Drop sync when unpacking.
            *StenoPacket._STRUCT.unpack(usb_packet[:StenoPacket.HEADER_SIZE])[1:]
        )
        if packet.data_length:
            packet.data, = unpack(
                '%ss' % packet.data_length,
                usb_packet[StenoPacket.HEADER_SIZE:StenoPacket.HEADER_SIZE + packet.data_length]
            )
        return packet

    @staticmethod
    def make_open_request(file_name=b'REALTIME.000', disk_id=b'A'):
        """Request to open a file on the writer, defaults to the realtime file."""
        return StenoPacket(
            packet_type=PacketType.OPEN_FILE,
            p1=ord(disk_id) if disk_id else 0, # Omitting p1 may use the default drive.
            data=file_name,
        )

    @staticmethod
    def make_read_request(file_offset=1, byte_count=MAX_READ):
        """Request to read from the writer, defaults to settings required when reading from realtime file."""
        return StenoPacket(
            packet_type=PacketType.READ_FILE,
            p1=file_offset,
            p2=byte_count,
        )

    @property
    def is_error(self):
        return self.packet_type == PacketType.ERROR

    @property
    def is_ok(self):
        return self.packet_type == PacketType.OK

    def strokes(self):
        """Get list of strokes represented in this packet's data"""

        # Expecting 8-byte chords (4 bytes of steno, 4 of timestamp.)
        assert self.data_length % 8 == 0
        # Steno should only be present on ACTION_READ packets
        assert self.packet_type == PacketType.READ_FILE

        return [
            Stroke.unpack(stroke_data)
            for stroke_data in grouper(8, self.data, 0)
        ]
