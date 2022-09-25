import os
import glob
from pathlib import Path
from setuptools import Extension, setup  # type: ignore

# Read the contents of the README file
LONG_DESCRIPTION = (Path(__file__).parent / "README.md").read_text()

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
    def __str__(self) -> str:
        return self.__fspath__()

    def __fspath__(self) -> str:
        import numpy

        include_path: str = numpy.get_include()
        return os.fspath(include_path)


# The gambatte extension, including libgambatte with the Cython wrapper
gambatte_extension = Extension(
    "gambaterm.libgambatte",
    language="c++",
    include_dirs=libgambatte_include_dirs + [NumpyIncludePath()],  # type: ignore
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
    version="0.12.0",
    packages=["gambaterm"],
    setup_requires=["setuptools>=42", "Cython>=0.29.13", "numpy"],
    ext_modules=[gambatte_extension, termblit_extension],
    install_requires=[
        "numpy>=1.20",
        "asyncssh>=2.9",
        "prompt_toolkit>=3.0.29",
        "sounddevice",
        "samplerate",
        "python-xlib; sys_platform == 'linux'",
        "pynput; sys_platform != 'linux'",
    ],
    extras_require={
        "controller-support": ["pygame>=1.9.5"],
    },
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "gambaterm = gambaterm:main",
            "gambaterm-ssh = gambaterm.ssh:main",
        ],
    },
    description="A terminal frontend for gambatte game boy color emulator ",
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    url="https://github.com/vxgmichel/gambatte-terminal",
    license="GPLv3",
    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    author="Vincent Michel",
    author_email="vxgmichel@gmail.com",
)
