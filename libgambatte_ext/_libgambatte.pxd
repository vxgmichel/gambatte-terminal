from libcpp.string cimport string
from libc.stdint cimport uint32_t


cdef extern from "gambatte.h" namespace "gambatte":
    ctypedef unsigned InputGetter(void *)

    cdef cppclass GB:
        GB() except +;
        int load(string& romfile, unsigned flags);
        ptrdiff_t runFor(
            uint32_t *videoBuf,
            ptrdiff_t pitch,
	        uint32_t *audioBuf,
            size_t& samples,
        ) nogil;
        void setInputGetter(InputGetter *getInput, void *context);
        void setSaveDir(string& sdir);

        # Save state
        void selectState(int state);
        int currentState();
        int loadState();
        int saveState(uint32_t *videoBuf, ptrdiff_t pitch);
