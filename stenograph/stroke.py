from itertools import compress

STENO_KEY_CHART = (
    ('^', '#', 'S-', 'T-', 'K-', 'P-'),
    ('W-', 'H-', 'R-', 'A-', 'O-', '*'),
    ('-E', '-U', '-F', '-R', '-P', '-B'),
    ('-L', '-G', '-T', '-S', '-D', '-Z'),
)

class Stroke:
    def __init__(self, keys):
        self.keys = keys

    def __repr__(self):
        return "Stroke([{0}])".format(", ".join(self.keys))

    @staticmethod
    def unpack(stroke_data):
        keys = []
        for steno_byte, key_chart_row in zip(stroke_data, STENO_KEY_CHART):
            assert steno_byte >= 0b11000000
            # Only interested in right 6 values
            key_mask = [int(i) for i in bin(steno_byte)[-6:]]
            keys.extend(compress(key_chart_row, key_mask))
        return Stroke(keys)
