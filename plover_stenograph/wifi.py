from plover.machine.base import ThreadedStenotypeBase
from plover import log
from time import sleep

import socket
import sys

from stenograph import *

# For UDP broadcast. Stenograph machines listen on port 5012 for opening packet.
# Response is sent on port 5015.
BROADCAST_ADDRESS = "255.255.255.255"
BROADCAST_PORT = 5012

# This is the specific reply by Stenograph machines to indicate their presence.
BATTLE_CRY = b'Calling All Miras...\x00\x00\x00\x00\x00\x00\x00\x00'

class StenographMachine(AbstractStenographMachine):
    
    def __init__(self):
        super(StenographMachine, self).__init__()
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
                    
        except client.timeout as e:
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

class Stenograph(ThreadedStenotypeBase):

    KEYS_LAYOUT = '''
        #  #  #  #  #  #  #  #  #  #
        S- T- P- H- * -F -P -L -T -D
        S- K- W- R- * -R -B -G -S -Z
              A- O-   -E -U
        ^
    '''
    KEYMAP_MACHINE_TYPE = 'Stentura'

    def __init__(self, params):
        super(Stenograph, self).__init__()
        self._machine = StenographMachine()

    def _on_stroke(self, keys):
        steno_keys = self.keymap.keys_to_actions(keys)
        if steno_keys:
            self._notify(steno_keys)

    def start_capture(self):
        self.finished.clear()
        self._initializing()
        """Begin listening for output from the stenotype machine."""
        if not self._connect_machine():
            log.warning('Writer not found. Try clicking refresh.')
            self._error()
        else:
            self._ready()
            self.start()

    def _connect_machine(self):
        connected = False
        try:
            connected = self._machine.connect()
        except AssertionError as e:
            log.warning('Error connecting: %s', e)
            self._error()
        except IOError as e:
            log.warning('Lost connection with Stenograph machine: %s', e)
            self._error()
        finally:
            return connected

    def _reconnect(self):
        self._initializing()
        connected = False
        while not self.finished.isSet() and not connected:
            sleep(0.25)
            connected = self._connect_machine()
        return connected

    def _send_receive(self, request):
        """Send a StenoPacket and return the response or raise exceptions."""
        log.debug('Requesting from Stenograph: %s', request)
        response = self._machine.send_receive(request)
        log.debug('Response from Stenograph: %s', response)
        if response is None:
            """No response implies device connection issue."""
            raise IOError()
        elif response.packet_id == StenoPacket.ID_ERROR:
            """Writer may reply with an error packet"""
            error_number = response.p1
            if error_number == 3:
                raise UnableToPerformRequestException()
            elif error_number == 7:
                raise FileNotAvailableException()
            elif error_number == 8:
                raise NoRealtimeFileException()
            elif error_number == 9:
                raise FinishedReadingClosedFileException()
        else:
            """Writer has returned a packet"""
            if (response.packet_id != request.packet_id
                    or response.sequence_number != request.sequence_number):
                raise ProtocolViolationException()
            return response

    def run(self):

        class ReadState(object):
            def __init__(self):
                self.realtime = False  # Not realtime until we get a 0-length response
                self.realtime_file_open = False  # We are reading from a file
                self.offset = 0  # File offset to read from

            def reset(self):
                self.__init__()

        state = ReadState()

        while not self.finished.isSet():
            try:
                if not state.realtime_file_open:
                    # Open realtime file
                    self._send_receive(StenoPacket.make_open_request())
                    state.realtime_file_open = True
                response = self._send_receive(
                    StenoPacket.make_read_request(file_offset=state.offset)
                )
            except IOError as e:
                log.warning(u'Stenograph writer disconnected, reconnecting…')
                log.debug('Stenograph exception: %s', e)

                # User could start a new file while disconnected.
                state.reset()
                if self._reconnect():
                    log.warning('Stenograph writer reconnected.')
                    self._ready()
            except NoRealtimeFileException:
                # User hasn't started writing, just keep opening the realtime file
                state.reset()
            except FinishedReadingClosedFileException:
                # File closed! Open the realtime file.
                state.reset()
            else:
                if response.data_length:
                    state.offset += response.data_length
                elif not state.realtime:
                    state.realtime = True
                if response.data_length and state.realtime:
                    for stroke in response.strokes():
                        self._on_stroke(stroke)

        self._machine.disconnect()

    def stop_capture(self):
        """Stop listening for output from the stenotype machine."""
        super(Stenograph, self).stop_capture()
        self._sock = None
        self._machine = None
