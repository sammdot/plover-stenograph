from stenograph.packet import ErrorType
from stenograph.exception import *

class MachineTransport:
    """Simple interface to connect with and send data to a Stenograph machine"""

    def connect(self):
        """Connect to machine, raise an exception if an error occurred"""
        raise NotImplementedError('connect() is not implemented')

    def disconnect(self):
        """Disconnect from the machine"""
        raise NotImplementedError('disconnect() is not implemented')

    def send_receive(self, request):
        """Send a StenoPacket to the machine and return the response"""
        raise NotImplementedError('send_receive() is not implemented')

    def handle_response(self, response):
        """Read the response, and raise an exception if an error occurred"""
        if response.is_error:
            error_type = ErrorType(response.p1)
            if error_type == ErrorType.UNABLE_TO_PERFORM:
                raise UnableToPerformRequestException
            elif error_type == ErrorType.FILE_NOT_AVAILABLE:
                raise FileNotAvailableException
            elif error_type == ErrorType.NO_REALTIME_FILE:
                raise NoRealtimeFileException
            elif error_type == ErrorType.FINISHED_READING_CLOSED_FILE:
                raise FinishedReadingClosedFileException
        return response
