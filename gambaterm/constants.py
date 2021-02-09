from enum import IntEnum

GB_WIDTH = 160
GB_HEIGHT = 144
GB_FPS = 59.727500569606
GB_TICKS_IN_FRAME = 35112


class GBInput(IntEnum):
    A = 0x01
    B = 0x02
    SELECT = 0x04
    START = 0x08
    RIGHT = 0x10
    LEFT = 0x20
    UP = 0x40
    DOWN = 0x80
