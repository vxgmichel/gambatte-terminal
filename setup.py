from __future__ import annotations

import glob
from pathlib import Path
from setuptools import Extension, setup

import numpy

# Read the contents of the README file
LONG_DESCRIPTION = (Path(__file__).parent / "README.md").read_text()

# List libgambatte sources, excluding `file_zip.cpp`
libgambatte_sources = [
    path
    for path in glob.glob("libgambatte/**/*.cpp", recursive=True)
    if not path.endswith("file_zip.cpp")
]

# List all directories containing `.h` files
libgambatte_include_dirs: list[str] = list(
    set(
        str(Path(path).parent)
        for path in glob.glob("libgambatte/**/*.h", recursive=True)
    )
)

# The gambatte extension, including libgambatte with the Cython wrapper
gambatte_extension = Extension(
    "gambaterm.libgambatte",
    language="c++",
    include_dirs=[
        *libgambatte_include_dirs,
        "libgambatte_ext",
        numpy.get_include(),
    ],
    extra_compile_args=["-DHAVE_STDINT_H"],
    sources=[
        *libgambatte_sources,
        "libgambatte_ext/libgambatte.pyx",
    ],
)


# The termblit extension
termblit_extension = Extension(
    "gambaterm.termblit",
    language="c",
    include_dirs=[numpy.get_include()],
    sources=["termblit_ext/termblit.pyx"],
)

setup(
    name="gambaterm",
    version="0.12.7",
    packages=["gambaterm"],
    ext_modules=[gambatte_extension, termblit_extension],
    install_requires=[
        "numpy~=1.20",
        "asyncssh~=2.9",
        "prompt_toolkit~=3.0.29",
        "sounddevice~=0.4",
        "samplerate~=0.1.0",  # See https://github.com/tuxu/python-samplerate/issues/19
        "python-xlib; sys_platform == 'linux'",
        "pynput; sys_platform != 'linux'",
    ],
    extras_require={
        "controller-support": ["pygame~=1.9.5"],
    },
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "gambaterm = gambaterm:main",
            "gambaterm-ssh = gambaterm.ssh:main",
        ],
    },
    package_data={"gambaterm": ["py.typed"]},
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
