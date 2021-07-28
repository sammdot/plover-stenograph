from plover import log
from plover.machine.base import ThreadedStenotypeBase

from stenograph import *


class StenographMachine(ThreadedStenotypeBase):

    KEYS_LAYOUT = """
        #  #  #  #  #  #  #  #  #  #
        S- T- P- H- * -F -P -L -T -D
        S- K- W- R- * -R -B -G -S -Z
              A- O-   -E -U
        ^
    """
    KEYMAP_MACHINE_TYPE = "Stentura"

    def __init__(self, transport, params):
        super().__init__()
        self._transport = transport

    def _on_stroke(self, keys):
        steno_keys = self.keymap.keys_to_actions(keys)
        if steno_keys:
            self._notify(steno_keys)

    def start_capture(self):
        self.finished.clear()
        self._initializing()
        try:
            self._transport.connect()
        except ConnectionError as e:
            log.error("Stenograph writer is not connected: %s" % e)
            self._error()
        except IOError as e:
            log.error("Lost connection to Stenograph writer: %s" % e)
            self._error()
        except Exception as e:
            log.error("Error connecting to Stenograph writer: %s" % e)
            self._error()
        else:
            self._ready()
            self.start()

    def _reconnect(self):
        self._error()
        while not self.finished.wait(0.25):
            try:
                self._initializing()
                self._transport.connect()
            except Exception as e:
                log.debug("Stenograph writer exception: %s" % e)
                self._error()
            else:
                break

    def _send_receive(self, request):
        """Send a StenoPacket and return the response or raise exceptions."""
        log.debug("Requesting from Stenograph writer: %s", request)
        response = self._transport.send_receive(request)
        log.debug("Response from Stenograph writer: %s", response)
        return response

    def run(self):

        class ReadState:
            def __init__(self):
                self.realtime = False  # Not realtime until we get a 0-length response
                self.realtime_file_open = False  # We are reading from a file
                self.offset = 0  # File offset to read from

            def reset(self):
                self.__init__()

        state = ReadState()

        # Tracks whether the machine *just* disconnected, or has been disconnected
        # for a while, to prevent showing the warning more times than needed.
        disconnected = False

        while not self.finished.isSet():
            try:
                if not state.realtime_file_open:
                    # Open realtime file
                    self._send_receive(StenoPacket.make_open_request())
                    state.realtime_file_open = True
                response = self._send_receive(
                    StenoPacket.make_read_request(file_offset=state.offset)
                )
            except ConnectionError as e:
                if not disconnected:
                    log.warning("Stenograph writer disconnected, attempting to reconnect")
                    disconnected = True
                log.debug("Stenograph writer exception: %s", e)
                # User could start a new file while disconnected.
                state.reset()
                self._reconnect()
            except NoRealtimeFileException:
                # User hasn"t started writing, just keep opening the realtime file
                state.reset()
            except FinishedReadingClosedFileException:
                # File closed! Open the realtime file.
                state.reset()
            else:
                if disconnected:
                    log.warning("Stenograph writer reconnected")
                    self._ready()
                    disconnected = False
                if response.data_length:
                    state.offset += response.data_length
                elif not state.realtime:
                    state.realtime = True
                if response.data_length and state.realtime:
                    for stroke in response.strokes():
                        self._on_stroke(stroke.keys)

        self._transport.disconnect()

    def stop_capture(self):
        super().stop_capture()
        self._transport = None
        self._stopped()
