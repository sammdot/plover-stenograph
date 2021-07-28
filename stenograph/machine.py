class AbstractStenographMachine(object):
    """Simple interface to connect with and send data to a Stenograph machine"""

    def connect(self) -> bool:
        """Connect to machine, returns connection status"""
        raise NotImplementedError('connect() is not implemented')

    def disconnect(self):
        """Disconnect from the machine"""
        raise NotImplementedError('disconnect() is not implemented')

    def send_receive(self, request):
        """Send a StenoPacket to the machine and return the response or None"""
        raise NotImplementedError('send_receive() is not implemented')
