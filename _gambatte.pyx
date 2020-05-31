# distutils: language = c++

cimport numpy as np
from libcpp.string cimport string
from libgambatte cimport GB as C_GB


cdef class GB:
    cdef C_GB c_gb  # Hold a C++ instance which we're wrapping

    def load(self, str rom_file, unsigned flags=0):
        return self.c_gb.load(rom_file.encode(), flags)

    def runFor(
        self,
        np.ndarray[np.uint32_t, ndim=2] video,
        ptrdiff_t pitch,
        np.ndarray[np.uint32_t, ndim=1] audio,
        size_t samples,
    ):
        cdef unsigned int* video_buffer = <unsigned int*> video.data
        cdef unsigned int* audio_buffer = <unsigned int*> audio.data
        result = self.c_gb.runFor(video_buffer, pitch, audio_buffer, samples)
        return result, samples
