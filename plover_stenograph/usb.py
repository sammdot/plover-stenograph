from time import sleep

import sys

from plover.machine.base import ThreadedStenotypeBase
from plover import log

from stenograph import *

VENDOR_ID = 0x112b

if sys.platform.startswith('win32'):
    from ctypes import (
        Structure,
        POINTER,
        c_ulonglong,
        windll,
        create_string_buffer,
        sizeof,
        byref,
        pointer,
        c_char,
    )
    from ctypes.wintypes import DWORD, HANDLE, BYTE
    import uuid

    # Class GUID for Stenograph USB Writer
    USB_WRITER_GUID = uuid.UUID('{c5682e20-8059-604a-b761-77c4de9d5dbf}')

    class DeviceInterfaceData(Structure):
        _fields_ = [
            ('cbSize', DWORD),
            ('InterfaceClassGuid', BYTE * 16),
            ('Flags', DWORD),
            ('Reserved', POINTER(c_ulonglong))
        ]

    # For Windows we directly call Windows API functions
    SetupDiGetClassDevs = windll.setupapi.SetupDiGetClassDevsA
    SetupDiEnumDeviceInterfaces = windll.setupapi.SetupDiEnumDeviceInterfaces
    SetupDiGetInterfaceDeviceDetail = (
        windll.setupapi.SetupDiGetDeviceInterfaceDetailA)
    CreateFile = windll.kernel32.CreateFileA
    ReadFile = windll.kernel32.ReadFile
    WriteFile = windll.kernel32.WriteFile
    CloseHandle = windll.kernel32.CloseHandle
    GetLastError = windll.kernel32.GetLastError

    INVALID_HANDLE_VALUE = -1
    ERROR_INSUFFICIENT_BUFFER = 122

    class StenographMachine(object):
        def __init__(self):
            self._usb_device = HANDLE(0)
            self._read_buffer = create_string_buffer(MAX_READ + StenoPacket.HEADER_SIZE)

        @staticmethod
        def _open_device_instance(device_info, guid):
            dev_interface_data = DeviceInterfaceData()
            dev_interface_data.cbSize = sizeof(dev_interface_data)

            status = SetupDiEnumDeviceInterfaces(
                device_info, None, guid.bytes, 0, byref(dev_interface_data))
            if status == 0:
                log.debug('status is zero')
                return INVALID_HANDLE_VALUE

            request_length = DWORD(0)
            # Call with None to see how big a buffer we need for detail data.
            SetupDiGetInterfaceDeviceDetail(
                device_info,
                byref(dev_interface_data),
                None,
                0,
                pointer(request_length),
                None
            )
            err = GetLastError()
            if err != ERROR_INSUFFICIENT_BUFFER:
                log.debug('last error not insufficient buffer')
                return INVALID_HANDLE_VALUE

            characters = request_length.value

            class DeviceDetailData(Structure):
                _fields_ = [('cbSize', DWORD),
                            ('DevicePath', c_char * characters)]

            dev_detail_data = DeviceDetailData()
            dev_detail_data.cbSize = 5

            # Now put the actual detail data into the buffer
            status = SetupDiGetInterfaceDeviceDetail(
                device_info, byref(dev_interface_data), byref(dev_detail_data),
                characters, pointer(request_length), None
            )
            if not status:
                log.debug('not status')
                return INVALID_HANDLE_VALUE
            log.debug('okay, creating file')
            return CreateFile(
                dev_detail_data.DevicePath,
                0xC0000000, 0x3, 0, 0x3, 0x80, 0
            )

        @staticmethod
        def _open_device_by_class_interface_and_instance(class_guid):
            device_info = SetupDiGetClassDevs(class_guid.bytes, 0, 0, 0x12)
            if device_info == INVALID_HANDLE_VALUE:
                log.debug('dev info is invalid handle')
                return INVALID_HANDLE_VALUE

            usb_device = StenographMachine._open_device_instance(
                device_info, class_guid)
            return usb_device

        def _usb_write_packet(self, request):
            bytes_written = DWORD(0)
            request_packet = request.pack()
            WriteFile(
                self._usb_device,
                request_packet,
                StenoPacket.HEADER_SIZE + request.data_length,
                byref(bytes_written),
                None
            )
            return bytes_written.value

        def _usb_read_packet(self):
            bytes_read = DWORD(0)
            ReadFile(
              self._usb_device,
              byref(self._read_buffer),
              MAX_READ + StenoPacket.HEADER_SIZE,
              byref(bytes_read),
              None
            )
            # Return None if not enough data was read.
            if bytes_read.value < StenoPacket.HEADER_SIZE:
                return None

            writer_packet = StenoPacket.unpack(self._read_buffer)
            return writer_packet

        def disconnect(self):
            CloseHandle(self._usb_device)
            self._usb_device = INVALID_HANDLE_VALUE

        def connect(self):
            # If already connected, disconnect first.
            if self._usb_device != INVALID_HANDLE_VALUE:
                self.disconnect()
            self._usb_device = (
                self._open_device_by_class_interface_and_instance(
                    USB_WRITER_GUID))
            return self._usb_device != INVALID_HANDLE_VALUE

        def send_receive(self, request):
            assert self._usb_device != INVALID_HANDLE_VALUE, 'device not open'
            written = self._usb_write_packet(request)
            if written < StenoPacket.HEADER_SIZE:
                # We were not able to write the request.
                return None
            writer_packet = self._usb_read_packet()
            return writer_packet
else:
    from usb import core, util

    class StenographMachine(AbstractStenographMachine):

        def __init__(self):
            super(StenographMachine, self).__init__()
            self._usb_device = None
            self._endpoint_in = None
            self._endpoint_out = None
            self._connected = False

        def connect(self):
            """Attempt to and return connection"""
            # Disconnect device if it's already connected.
            if self._connected:
                self.disconnect()

            # Find the device by the vendor ID.
            usb_device = core.find(idVendor=VENDOR_ID)
            if not usb_device:  # Device not found
                return self._connected

            # Copy the default configuration.
            usb_device.set_configuration()
            config = usb_device.get_active_configuration()
            interface = config[(0, 0)]

            # Get the write endpoint.
            endpoint_out = util.find_descriptor(
                interface,
                custom_match=lambda e:
                    util.endpoint_direction(e.bEndpointAddress) ==
                    util.ENDPOINT_OUT
            )
            assert endpoint_out is not None, 'cannot find write endpoint'

            # Get the read endpoint.
            endpoint_in = util.find_descriptor(
                interface,
                custom_match=lambda e:
                    util.endpoint_direction(e.bEndpointAddress) ==
                    util.ENDPOINT_IN
            )
            assert endpoint_in is not None, 'cannot find read endpoint'

            self._usb_device = usb_device
            self._endpoint_in = endpoint_in
            self._endpoint_out = endpoint_out
            self._connected = True
            return self._connected

        def disconnect(self):
            self._connected = False
            util.dispose_resources(self._usb_device)
            self._usb_device = None
            self._endpoint_in = None
            self._endpoint_out = None

        def send_receive(self, request):
            assert self._connected, 'cannot read from machine if not connected'
            try:
                self._endpoint_out.write(request.pack())
                response = self._endpoint_in.read(
                    MAX_READ + StenoPacket.HEADER_SIZE, 3000)
            except core.USBError:
                return None
            else:
                if response and len(response) >= StenoPacket.HEADER_SIZE:
                    writer_packet = StenoPacket.unpack(response)
                    # Ignore data if sequence numbers don't match.
                    if writer_packet.sequence_number == request.sequence_number:
                        return writer_packet
                return None


class ProtocolViolationException(Exception):
    """The writer did something unexpected"""
    pass


class UnableToPerformRequestException(Exception):
    """The writer cannot perform the action requested"""
    pass


class FileNotAvailableException(Exception):
    """The writer cannot read from the current file"""
    pass


class NoRealtimeFileException(Exception):
    """The realtime file doesn't exist, likely because the user hasn't started writing"""
    pass


class FinishedReadingClosedFileException(Exception):
    """The closed file being read is complete and cannot be read further"""
    pass


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
                        self._on_stroke(stroke)

        self._machine.disconnect()

    def stop_capture(self):
        """Stop listening for output from the stenotype machine."""
        super(Stenograph, self).stop_capture()
        self._machine = None
        self._stopped()
