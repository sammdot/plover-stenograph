class ConnectionError(Exception):
    """We could not connect to the writer."""
    pass

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
