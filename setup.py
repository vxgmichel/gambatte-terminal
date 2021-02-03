import os
import glob
from setuptools import Extension, setup

# List libgambatte sources, excluding `file_zip.cpp`
libgambatte_sources = [
    path
    for path in glob.glob("libgambatte/**/*.cpp", recursive=True)
    if not path.endswith("file_zip.cpp")
]

# List all directories containing `.h` files
libgambatte_include_dirs = list(
    set(
        os.path.dirname(path)
        for path in glob.glob("libgambatte/**/*.h", recursive=True)
    )
)


# Defer call to `numpy.get_include`
class NumpyIncludePath(os.PathLike):
    def __str__(self):
        return self.__fspath__()

    def __fspath__(self):
        import numpy

        return os.fspath(numpy.get_include())


# The gambatte extension, including libgambatte with the Cython wrapper
gambatte_extension = Extension(
    "gambaterm.libgambatte",
    language="c++",
    include_dirs=libgambatte_include_dirs + [NumpyIncludePath()],
    extra_compile_args=["-DHAVE_STDINT_H"],
    sources=libgambatte_sources + ["libgambatte_ext/libgambatte.pyx"],
)


# The termblit extension
termblit_extension = Extension(
    "gambaterm.termblit",
    language="c",
    include_dirs=[NumpyIncludePath()],
    sources=["termblit_ext/termblit.pyx"],
)

setup(
    name="gambaterm",
    version="0.7.0",
    packages=["gambaterm"],
    setup_requires=["setuptools>=42", "Cython>=0.29.13", "numpy"],
    ext_modules=[gambatte_extension, termblit_extension],
    install_requires=[
        "numpy>=1",
        "asyncssh>=2",
        "prompt_toolkit>=3",
        "sounddevice",
        "samplerate",
        "xlib; sys_platform == 'linux'",
        "keyboard; sys_platform != 'linux'",
    ],
    python_requires=">=3.6",
    entry_points={
        "console_scripts": [
            "gambaterm = gambaterm:main",
            "gambaterm-ssh = gambaterm.ssh:main",
        ],
    },
    description="A terminal frontend for gambatte game boy color emulator ",
    url="https://github.com/vxgmichel/gambatte-terminal",
    license="GPLv3",
    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
    ],
    author="Vincent Michel",
    author_email="vxgmichel@gmail.com",
)
