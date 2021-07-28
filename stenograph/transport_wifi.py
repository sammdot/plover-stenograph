from plover import log
from time import sleep
import socket

from stenograph.transport import MachineTransport
from stenograph.packet import MAX_READ, StenoPacket


# For UDP broadcast. Stenograph machines listen on port 5012 for opening packet.
# Response is sent on port 5015.
BROADCAST_ADDRESS = "255.255.255.255"
BROADCAST_PORT = 5012

# This is the specific reply by Stenograph machines to indicate their presence.
BATTLE_CRY = b'Calling All Miras...\x00\x00\x00\x00\x00\x00\x00\x00'


class WiFiTransport(MachineTransport):

    def __init__(self):
        super().__init__()
        self._connected = False
        self._sock = None
        self._stenograph_address = None

    def find_stenograph(self):
        try:
            log.warning("Searching for Wi-Fi Stenographs...")
            udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            udp.settimeout(10)

            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            while self._stenograph_address == None:
                udp.sendto(BATTLE_CRY, (BROADCAST_ADDRESS, BROADCAST_PORT))
                sleep(1.2)

                data, address = udp.recvfrom(65565)
            
                if "Mira in the neighborhood" in data.decode("utf-8"):
                    self._stenograph_address = address
                    udp.close()
                    break
                    
        except socket.timeout as e:
            log.warning('Client timed out: %s' % e)
        
        return self._stenograph_address

    def connect(self):
        """Attempt to connect and return connection"""

        # Disconnect device if it's already connected.
        if self._connected:
            self.disconnect()

        # Find IP of Stenograph machine.
        self._stenograph_address = self.find_stenograph()

        # No IP address = no device found.
        if not self._stenograph_address:
            return self._connected

        # Now create a TCP connection to the found machine's IP address.
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((self._stenograph_address[0], 80))
            self._sock = sock
            log.warning('Stenograph writer found at IP address: %s!' % self._stenograph_address[0])
        except socket.timeout as e:
            log.warning('Stenograph writer timed out: %s' % e)
        except socket.error as exc:
            log.warning('Stenograph writer binding error: %s' % exc)

        self._connected = True

        return self._connected

    def disconnect(self):
        self._sock.close()
        self._connected = False
        self._stenograph_address = None

    def send_receive(self, request):
        assert self._connected, 'Cannot read from machine if not connected.'
        try:
            # Send packet
            self._sock.send(request.pack())

            # Buffer size = MAX_READ + StenoPacket.HEADER_SIZE
            response = self._sock.recv(MAX_READ + StenoPacket.HEADER_SIZE)
        except OSError:
            return None
        except socket.error:
            return None
        except:
            return None
        else:
            if response and len(response) >= StenoPacket.HEADER_SIZE:
                writer_packet = StenoPacket.unpack(response)
                # Ignore data if sequence numbers don't match.
                if writer_packet.sequence_number == request.sequence_number:
                    return writer_packet
            return None
