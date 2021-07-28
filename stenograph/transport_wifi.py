from threading import Event
import socket

from stenograph.transport import MachineTransport
from stenograph.packet import MAX_READ, StenoPacket
from stenograph.exception import ProtocolViolationException, ConnectionError


# For UDP broadcast. Stenograph machines listen on port 5012 for opening packet.
# Response is sent on port 5015.
BROADCAST_ADDRESS = "255.255.255.255"
BROADCAST_PORT = 5012

# This is the specific reply by Stenograph machines to indicate their presence.
BATTLE_CRY = b"Calling All Miras...\x00\x00\x00\x00\x00\x00\x00\x00"
MACHINE_RESPONSE = b"Mira in the neighborhood "


class WiFiTransport(MachineTransport):

    def __init__(self):
        super().__init__()
        self._connected = False
        self._sock = None
        self._stenograph_address = None

    def find_stenograph(self):
        try:
            udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            udp.settimeout(10)

            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            found_machine = Event()

            while not found_machine.wait(1.2):
                udp.sendto(BATTLE_CRY, (BROADCAST_ADDRESS, BROADCAST_PORT))
                data, address = udp.recvfrom(65565)
                if MACHINE_RESPONSE in data:
                    self._stenograph_address = address
                    udp.close()
                    found_machine.set()

        except socket.timeout as e:
            raise ConnectionError("Client timed out: %s" % e)
        
        return self._stenograph_address

    def connect(self):
        """Attempt to connect and return connection"""
        if self._connected:
            self.disconnect()

        self._stenograph_address = self.find_stenograph()

        # No IP address = no device found.
        if not self._stenograph_address:
            raise ConnectionError("Could not find Stenograph writer")

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((self._stenograph_address[0], 80))
            self._sock = sock
        except socket.timeout as e:
            raise ConnectionError("Stenograph writer timed out: %s" % e)
        except socket.error as e:
            raise ConnectionError("Stenograph writer binding error: %s" % e)

        self._connected = True

    def disconnect(self):
        if self._sock:
            self._sock.close()
            self._sock = None
        self._connected = False
        self._stenograph_address = None

    def send_receive(self, request):
        assert self._connected, "Cannot read from machine if not connected."
        try:
            self._sock.send(request.pack())

            # Buffer size = MAX_READ + StenoPacket.HEADER_SIZE
            response = self._sock.recv(MAX_READ + StenoPacket.HEADER_SIZE)
        except Exception as e:
            raise ConnectionError(e)
        else:
            if response and len(response) >= StenoPacket.HEADER_SIZE:
                writer_packet = StenoPacket.unpack(response)
                if (writer_packet.sequence_number == request.sequence_number and
                    writer_packet.packet_type == request.packet_type):
                    return self.handle_response(writer_packet)
                raise ProtocolViolationException()
            raise ConnectionError("No response from writer")
