from setuptools import setup, Extension

from Cython.Build import cythonize

setup(ext_modules=cythonize([
    Extension(
        "_gambatte",
        ["_gambatte.pyx"],
        #libraries=["gambatte"],
        #extra_objects=["libgambatte.a"]
    )])
)
