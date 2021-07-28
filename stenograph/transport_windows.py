from ctypes import windll, wintypes
import ctypes
import uuid
from plover import log

from stenograph.transport import MachineTransport
from stenograph.packet import MAX_READ, StenoPacket


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


class WindowsUsbTransport(MachineTransport):

    def __init__(self):
        super().__init__()
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
