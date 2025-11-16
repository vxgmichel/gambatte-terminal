from libcpp.string cimport string
from libc.stdint cimport uint32_t

cdef extern from "gambatte.h" namespace "gambatte":
    cdef cppclass GB:
        GB() except +;
        int load(string& romfile, unsigned flags);
        ptrdiff_t runFor(
            uint32_t *videoBuf,
            ptrdiff_t pitch,
	        uint32_t *audioBuf,
            size_t& samples,
        );
        void setInputGetter(GetInput *getInput);
        void setSaveDir(string& sdir);

        # Save state
        void selectState(int state);
        int currentState();
        int loadState();
        int saveState(uint32_t *videoBuf, ptrdiff_t pitch);


cdef extern from "input.h" namespace "gambatte":
    cdef cppclass GetInput:
        unsigned int value;
