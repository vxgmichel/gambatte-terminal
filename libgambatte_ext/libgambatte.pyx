# distutils: language = c++
# distutils: libraries = gambatte

cimport numpy as np
from libcpp.string cimport string
from _libgambatte cimport GB as C_GB
from _libgambatte cimport GetInput as C_GetInput


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

    def set_save_directory(self, str path):
        self.c_gb.setSaveDir(path.encode())
