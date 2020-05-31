# distutils: language = c++

from libgambatte cimport GB

cdef class PyGB:
    cdef GB c_gb  # Hold a C++ instance which we're wrapping

    def load(self, rom_file, flags=0):
        return self.c_rect.load(rom_file, flags)
