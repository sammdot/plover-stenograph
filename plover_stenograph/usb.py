from time import sleep

import sys

from plover.machine.base import ThreadedStenotypeBase
from plover import log

from stenograph import *

VENDOR_ID = 0x112b

if sys.platform.startswith('win32'):

    # For Windows we directly call Windows API functions.

    from ctypes import windll, wintypes
    import ctypes
    import uuid

    GUID = wintypes.BYTE * 16
    HDEVINFO = wintypes.HANDLE

    # Stubs.
    LPOVERLAPPED = wintypes.LPVOID
    LPSECURITY_ATTRIBUTES = wintypes.LPVOID
    PSP_DEVINFO_DATA = wintypes.LPVOID

    # Class GUID for Stenograph USB Writer.
    USB_WRITER_GUID = GUID(*uuid.UUID('{c5682e20-8059-604a-b761-77c4de9d5dbf}').bytes)

    class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
        _fields_ = [
            ('cbSize', wintypes.DWORD),
            ('InterfaceClassGuid', GUID),
            ('Flags', wintypes.DWORD),
            ('Reserved', wintypes.PULONG),
        ]
    PSP_DEVICE_INTERFACE_DATA = ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)

    class SP_DEVICE_INTERFACE_DETAIL_DATA_A(ctypes.Structure):
        _fields_ = [
            ('cbSize', wintypes.DWORD),
            ('_DevicePath', wintypes.CHAR * 1),
        ]
        @property
        def DevicePath(self):
            return ctypes.string_at(ctypes.byref(self, ctypes.sizeof(wintypes.DWORD)))
    PSP_DEVICE_INTERFACE_DETAIL_DATA_A = ctypes.POINTER(SP_DEVICE_INTERFACE_DETAIL_DATA_A)

    SetupDiGetClassDevs = windll.setupapi.SetupDiGetClassDevsA
    SetupDiGetClassDevs.argtypes = [
        ctypes.POINTER(GUID), # ClassGuid
        wintypes.LPCWSTR,     # Enumerator
        wintypes.HWND,        # hwndParent
        wintypes.DWORD,       # Flags
    ]
    SetupDiGetClassDevs.restype = HDEVINFO

    SetupDiDestroyDeviceInfoList = windll.setupapi.SetupDiDestroyDeviceInfoList
    SetupDiDestroyDeviceInfoList.argtypes = [
        HDEVINFO, # DeviceInfoSet
    ]
    SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

    SetupDiEnumDeviceInterfaces = windll.setupapi.SetupDiEnumDeviceInterfaces
    SetupDiEnumDeviceInterfaces.argtypes = [
        HDEVINFO,                  # DeviceInfoSet
        PSP_DEVINFO_DATA,          # DeviceInfoData
        ctypes.POINTER(GUID),      # InterfaceClassGuid
        wintypes.DWORD,            # MemberIndex
        PSP_DEVICE_INTERFACE_DATA, # DeviceInterfaceData
    ]
    SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL

    SetupDiGetDeviceInterfaceDetail = windll.setupapi.SetupDiGetDeviceInterfaceDetailA
    SetupDiGetDeviceInterfaceDetail.argtypes = [
        HDEVINFO,                           # DeviceInfoSet
        PSP_DEVICE_INTERFACE_DATA,          # DeviceInterfaceData
        PSP_DEVICE_INTERFACE_DETAIL_DATA_A, # DeviceInterfaceDetailData
        wintypes.DWORD,                     # DeviceInterfaceDetailDataSize
        wintypes.PDWORD,                    # RequiredSize
        PSP_DEVINFO_DATA,                   # DeviceInfoData
    ]
    SetupDiGetDeviceInterfaceDetail.restype = wintypes.BOOL

    CreateFile = windll.kernel32.CreateFileA
    CreateFile.argtypes = [
        wintypes.LPCSTR,       # lpFileName
        wintypes.DWORD,        # dwDesiredAccess
        wintypes.DWORD,        # dwShareMode
        LPSECURITY_ATTRIBUTES, # lpSecurityAttributes
        wintypes.DWORD,        # dwCreationDisposition
        wintypes.DWORD,        # dwFlagsAndAttributes
        wintypes.HANDLE,       # hTemplateFile
    ]
    CreateFile.restype = wintypes.HANDLE

    ReadFile = windll.kernel32.ReadFile
    ReadFile.argtypes = [
        wintypes.HANDLE,  # hFile
        wintypes.LPVOID,  # lpBuffer
        wintypes.DWORD,   # nNumberOfBytesToRead
        wintypes.LPDWORD, # lpNumberOfBytesRead
        LPOVERLAPPED,     # lpOverlapped
    ]
    ReadFile.restype = wintypes.BOOL

    WriteFile = windll.kernel32.WriteFile
    WriteFile.argtypes = [
        wintypes.HANDLE,  # hFile
        wintypes.LPCVOID, # lpBuffer
        wintypes.DWORD,   # nNumberOfBytesToWrite
        wintypes.LPDWORD, # lpNumberOfBytesWritten
        LPOVERLAPPED,     # lpOverlapped
    ]
    WriteFile.restype = wintypes.BOOL

    CloseHandle = windll.kernel32.CloseHandle
    CloseHandle.argtypes = [
        wintypes.HANDLE, # hObject
    ]
    CloseHandle.restype = wintypes.BOOL

    # Defines.

    CREATE_ALWAYS = 2
    CREATE_NEW    = 1

    DIGCF_DEVICEINTERFACE = 0x00000010
    DIGCF_PRESENT         = 0x00000002

    ERROR_INSUFFICIENT_BUFFER = 0x0000007A
    ERROR_NO_MORE_ITEMS       = 0x00000103

    FILE_ATTRIBUTE_NORMAL = 0x80

    FILE_SHARE_READ  = 0x00000001
    FILE_SHARE_WRITE = 0x00000002

    GENERIC_READ  = 0x80000000
    GENERIC_WRITE = 0x40000000

    INVALID_HANDLE_VALUE = -1

    class StenographMachine:

        def __init__(self):
            self._usb_device = INVALID_HANDLE_VALUE
            self._read_buffer = ctypes.create_string_buffer(MAX_READ + StenoPacket.HEADER_SIZE)

        @staticmethod
        def _open_device_instance(device_info, guid):
            dev_interface_data = SP_DEVICE_INTERFACE_DATA()
            dev_interface_data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)

            if not SetupDiEnumDeviceInterfaces(
                device_info, None, ctypes.byref(guid),
                0, ctypes.byref(dev_interface_data)
            ):
                if ctypes.GetLastError() != ERROR_NO_MORE_ITEMS:
                    log.error('SetupDiEnumDeviceInterfaces: %s', ctypes.WinError())
                return INVALID_HANDLE_VALUE

            request_length = wintypes.DWORD(0)
            status = SetupDiGetDeviceInterfaceDetail(
                device_info,
                ctypes.byref(dev_interface_data),
                # Call with (None, 0) to see how big a buffer is needed.
                None, 0,
                ctypes.pointer(request_length),
                None,
            )
            if status or ctypes.GetLastError() != ERROR_INSUFFICIENT_BUFFER:
                log.debug('last error not insufficient buffer: %s', ctypes.WinError())
                return INVALID_HANDLE_VALUE

            dev_detail_data_buffer = ctypes.create_string_buffer(request_length.value)
            dev_detail_data_ptr = ctypes.cast(dev_detail_data_buffer, PSP_DEVICE_INTERFACE_DETAIL_DATA_A)
            dev_detail_data_ptr[0].cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA_A)

            # Now put the actual detail data into the buffer
            if not SetupDiGetDeviceInterfaceDetail(
                device_info,
                ctypes.byref(dev_interface_data),
                dev_detail_data_ptr,
                ctypes.sizeof(dev_detail_data_buffer),
                None,
                None,
            ):
                log.error('SetupDiGetDeviceInterfaceDetail: %s', ctypes.WinError())
                return INVALID_HANDLE_VALUE

            device_path = dev_detail_data_ptr[0].DevicePath

            log.debug('okay, creating file, device path: %s', device_path)

            handle = CreateFile(device_path,
                                GENERIC_READ | GENERIC_WRITE,
                                FILE_SHARE_READ | FILE_SHARE_WRITE,
                                None,
                                CREATE_ALWAYS | CREATE_NEW,
                                FILE_ATTRIBUTE_NORMAL,
                                None)
            if handle == INVALID_HANDLE_VALUE:
                log.error('CreateFile: %s', ctypes.WinError())
            return handle

        @staticmethod
        def _open_device_by_class_interface_and_instance(class_guid):
            device_info = SetupDiGetClassDevs(ctypes.byref(class_guid), None, None,
                                              DIGCF_DEVICEINTERFACE | DIGCF_PRESENT)
            if device_info == INVALID_HANDLE_VALUE:
                log.error('SetupDiGetClassDevs: %s', ctypes.WinError())
                return INVALID_HANDLE_VALUE
            usb_device = StenographMachine._open_device_instance(device_info, class_guid)
            if not SetupDiDestroyDeviceInfoList(device_info):
                log.error('SetupDiDestroyDeviceInfoList: %s', ctypes.WinError())
            return usb_device

        def _usb_write_packet(self, request):
            bytes_written = wintypes.DWORD(0)
            request_packet = request.pack()
            if not WriteFile(self._usb_device,
                             request_packet,
                             StenoPacket.HEADER_SIZE + request.data_length,
                             ctypes.byref(bytes_written),
                             None):
                log.error('WriteFile: %s', ctypes.WinError())
                return 0
            return bytes_written.value

        def _usb_read_packet(self):
            bytes_read = wintypes.DWORD(0)
            if not ReadFile(self._usb_device,
                            self._read_buffer,
                            MAX_READ + StenoPacket.HEADER_SIZE,
                            ctypes.byref(bytes_read),
                            None):
                log.error('ReadFile: %s', ctypes.WinError())
                return None
            # Return None if not enough data was read.
            if bytes_read.value < StenoPacket.HEADER_SIZE:
                log.error('ReadFile: short read, %u < %u',
                          bytes_read.value, StenoPacket.HEADER_SIZE)
                return None
            writer_packet = StenoPacket.unpack(self._read_buffer)
            return writer_packet

        def disconnect(self):
            if not CloseHandle(self._usb_device):
                log.error('CloseHandle: %s', ctypes.WinError())
            self._usb_device = INVALID_HANDLE_VALUE

        def connect(self):
            # If already connected, disconnect first.
            if self._usb_device != INVALID_HANDLE_VALUE:
                self.disconnect()
            self._usb_device = self._open_device_by_class_interface_and_instance(USB_WRITER_GUID)
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
            super().__init__()
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
