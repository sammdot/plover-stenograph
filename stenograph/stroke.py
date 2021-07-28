from itertools import compress

STENO_KEY_CHART = (
  ('^', '#', 'S-', 'T-', 'K-', 'P-'),
  ('W-', 'H-', 'R-', 'A-', 'O-', '*'),
  ('-E', '-U', '-F', '-R', '-P', '-B'),
  ('-L', '-G', '-T', '-S', '-D', '-Z'),
)

STENO_KEY_ORDER = sum(STENO_KEY_CHART, ())
