from libcpp.string cimport string

cdef extern from "include/gambatte.h" namespace "gambatte":
    cdef cppclass GB:
        GB() except +;
        int load(string romfile, unsigned flags = 0);
