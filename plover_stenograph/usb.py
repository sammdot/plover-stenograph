from plover.machine.base import ThreadedStenotypeBase
from plover import log
from time import sleep

from stenograph import *


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
        self._machine = UsbTransport()

    def _on_stroke(self, keys):
        steno_keys = self.keymap.keys_to_actions(keys)
        if steno_keys:
            self._notify(steno_keys)

    def start_capture(self):
        self.finished.clear()
        self._initializing()
        """Begin listening for output from the stenotype machine."""
        if not self._connect_machine():
            log.warning('Stenograph machine is not connected')
            self._error()
        else:
            self._ready()
            self.start()

    def _connect_machine(self):
        connected = False
        try:
            connected = self._machine.connect()
        except ValueError:
            log.warning('Libusb must be installed.')
            self._error()
        except AssertionError as e:
            log.warning('Error connecting: %s', e)
            self._error()
        except Exception as e:
            log.warning("error: %s", e)
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
        elif response.is_error:
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
            if (response.packet_type != request.packet_type
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
                log.warning(u'Stenograph machine disconnected, reconnecting…')
                log.debug('Stenograph exception: %s', e)
                # User could start a new file while disconnected.
                state.reset()
                if self._reconnect():
                    log.warning('Stenograph reconnected.')
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
                        self._on_stroke(stroke.keys)

        self._machine.disconnect()

    def stop_capture(self):
        """Stop listening for output from the stenotype machine."""
        super(Stenograph, self).stop_capture()
        self._machine = None
        self._stopped()
