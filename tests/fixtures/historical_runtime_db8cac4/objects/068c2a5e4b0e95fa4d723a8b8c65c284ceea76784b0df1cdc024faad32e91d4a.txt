"""Bounded annotation press-pair recognition, independent of native keymaps.

Blender modal handlers need not receive DOUBLE_CLICK. A completed, unmoved first
click followed by a nearby press on the same label is therefore recognized here.
This transient state is never part of a sketch, journal or saved draft.
"""

import math


class DimensionClick:
    def __init__(self):
        self.reset()

    def reset(self):
        self._pressed = self._completed = None

    def press(self, identifier, position, timestamp, *, native_double=False):
        previous = self._completed
        self.reset()
        if native_double or (
            previous is not None
            and previous[0] == identifier
            and 0 <= timestamp - previous[2] <= 0.35
            and math.dist(position, previous[1]) <= 4
        ):
            return True
        self._pressed = (identifier, tuple(position), timestamp)
        return False

    def move(self, position):
        if self._pressed is not None and math.dist(position, self._pressed[1]) > 4:
            self.reset()
        elif self._completed is not None and math.dist(position, self._completed[1]) > 4:
            self.reset()

    def release(self, position):
        self.move(position)
        self._completed, self._pressed = self._pressed, None
