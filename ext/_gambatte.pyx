# distutils: language = c++
# distutils: libraries = gambatte

cimport numpy as np
from libcpp.string cimport string
from libgambatte cimport GB as C_GB
from libgambatte cimport GetInput as C_GetInput
from libc.stdio cimport sprintf


cdef class GB:
    cdef C_GB c_gb
    cdef C_GetInput c_getinput

    def __cinit__(self):
        self.c_gb.setInputGetter(&self.c_getinput)

    def load(self, str rom_file, unsigned flags=0):
        return self.c_gb.load(rom_file.encode(), flags)

    def run_for(
        self,
        np.ndarray[np.int32_t, ndim=2] video,
        ptrdiff_t pitch,
        np.ndarray[np.int32_t, ndim=1] audio,
        size_t samples,
    ):
        cdef unsigned int* video_buffer = <unsigned int*> video.data
        cdef unsigned int* audio_buffer = <unsigned int*> audio.data
        result = self.c_gb.runFor(video_buffer, pitch, audio_buffer, samples)
        return result, samples

    def set_input(self, unsigned int value):
        self.c_getinput.value = value


cdef char* move_absolute(char* buff, int x, int y):
    buff += sprintf(buff, "\033[%d;%dH", x, y)
    return buff


cdef char* move_relative(char* buff, int dx, int dy):
    # Vertical move
    if dx < -1:
        buff += sprintf(buff, "\033[%dA", -dx)
    elif dx == -1:
        buff += sprintf(buff, "\033[A")
    elif dx == 1:
        buff += sprintf(buff, "\033[B")
    elif dx > 1:
        buff += sprintf(buff, "\033[%dB", dx)
    # Horizontal move
    if dy < -1:
        buff += sprintf(buff, "\033[%dD", -dy)
    elif dy == -1:
        buff += sprintf(buff, "\033[D")
    elif dy == 1:
        buff += sprintf(buff, "\033[C")
    elif dy > 1:
        buff += sprintf(buff, "\033[%dC", dy)
    return buff



cdef int scale_256_to_6_shift(int x):
    x >>= 5
    x -= x > 0
    x -= x > 1
    return x


cdef int scale_256_to_6_closest(int x):
    if x < 48:
        return 0
    if x < 115:
        return 1
    return (x - 35) // 40

cdef int scale_256_to_6_spread(int x):
    return x // 43


cdef char* set_color(char* buff, int n, int true_color, int foreground):
    cdef int c
    cdef int b = n & 0xff
    cdef int g = (n >> 8) & 0xff
    cdef int r = (n >> 16) & 0xff
    if true_color:
        if foreground:
            buff += sprintf(buff, "\033[38;2;%d;%d;%dm", r, g, b)
        else:
            buff += sprintf(buff, "\033[48;2;%d;%d;%dm", r, g, b)
    else:
        b = scale_256_to_6_shift(b)
        g = scale_256_to_6_shift(g)
        r = scale_256_to_6_shift(r)
        c = 16 + 36 * r + 6 * g + b
        if foreground:
            buff += sprintf(buff, "\033[38;5;%dm", c)
        else:
            buff += sprintf(buff, "\033[48;5;%dm", c)
    return buff


cdef char* set_background(char* buff, int n, int true_color):
    return set_color(buff, n, true_color, False)


cdef char* set_foreground(char* buff, int n, int true_color):
    return set_color(buff, n, true_color, True)


cdef char* move_from_to(
    char *buff, int from_x, int from_y, int to_x, int to_y
):
    return move_relative(buff, to_x - from_x, to_y - from_y)


def paint_frame(
    np.ndarray[np.int32_t, ndim=2] video,
    np.ndarray[np.int32_t, ndim=2] last,
    int refx, int refy, int width, int height,
    int true_color,
):
    cdef char[144*160*100] base
    cdef char* result = base
    cdef int current_x = refx
    cdef int current_y = refy
    cdef int current_fg = -1
    cdef int current_bg = -1
    cdef int row_index, column_index
    cdef int color1, color2
    cdef int new_x, new_y
    cdef int invert_print

    # Move at reference point
    result = move_absolute(result, refx, refy)

    # Loop over terminal cells
    for row_index in range(min(height - refx, 144 // 2)):
        for column_index in range(min(width - refy, 160)):

            # Extract colors
            color1 = video[2 * row_index + 0, column_index]
            color2 = video[2 * row_index + 1, column_index]

            # Skip if identical to last printed frame
            if (
                last is not None and
                last[2 * row_index + 0, column_index] == color1 and
                last[2 * row_index + 1, column_index] == color2
            ):
                continue

            # Go to the new position
            new_x, new_y = row_index + refx, column_index + refy
            result = move_from_to(result, current_x, current_y, new_x, new_y)
            current_x, current_y = new_x, new_y

            # Print full block
            if color1 == color2 == current_fg != current_bg:
                result += sprintf(result, "\xe2\x96\x88")
                current_y += 1
                continue

            # Print empty block (space)
            if color1 == color2:
                if color1 != current_bg:
                    result = set_background(result, color1, true_color)
                    current_bg = color1
                result += sprintf(result, " ")
                current_y += 1
                continue

            # Detect print type
            invert_print = (
                current_fg == color1 or current_bg == color2 or
                current_fg != color2 and current_bg != color1
            )

            # Inverted print
            if invert_print:
                color1, color2 = color2, color1

            # Set background and foreground colors if necessary
            if current_fg != color1:
                result = set_foreground(result, color1, true_color)
                current_fg = color1
            if current_bg != color2:
                result = set_background(result, color2, true_color)
                current_bg = color2

            # Print lower half block
            if invert_print:
                result += sprintf(result, "\xe2\x96\x84")
                current_y += 1

            # Print upper half block
            else:
                result += sprintf(result, "\xe2\x96\x80")
                current_y += 1

    return base[:result-base]
