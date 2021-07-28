from usb import core, util

from stenograph.transport import MachineTransport
from stenograph.packet import MAX_READ, StenoPacket
from stenograph.exception import ProtocolViolationException, ConnectionError


VENDOR_ID = 0x112b


class LibusbTransport(MachineTransport):

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
            raise ConnectionError("USB device not connected")

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

    def disconnect(self):
        self._connected = False
        if self._usb_device:
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
