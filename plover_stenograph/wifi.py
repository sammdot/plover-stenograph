from stenograph import WiFiTransport
from plover_stenograph.base import StenographMachine


class StenographWiFi(StenographMachine):

    def __init__(self, params):
        super().__init__(WiFiTransport(), params)
