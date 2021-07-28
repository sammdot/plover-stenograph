from stenograph import UsbTransport
from plover_stenograph.base import StenographMachine


class StenographUsb(StenographMachine):

    def __init__(self, params):
        super().__init__(UsbTransport(), params)
