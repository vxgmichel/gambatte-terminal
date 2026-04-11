from __future__ import annotations

import glob
import platform
from setuptools import Extension, setup


def get_extensions() -> list[Extension]:
    import numpy  # Lazy import; numpy provided via build-system requires

    # Gather all C++ sources (including file_zip.cpp for ZIP support)
    # Exclude file.cpp since file_zip.cpp provides the full implementation
    libgambatte_sources = [
        p
        for p in glob.glob("gambatte-core/libgambatte/src/**/*.cpp", recursive=True)
        if not p.endswith(
            "file.cpp"
        )  # Exclude file.cpp because file_zip.cpp is included
    ]

    # Add unzip C sources for ZIP support
    libgambatte_sources += glob.glob(
        "gambatte-core/libgambatte/src/file/unzip/*.c", recursive=True
    )

    # Add zlib library for ZIP support
    libraries = []
    if platform.system() == "Windows":
        libraries += ["zlib"]
    else:
        libraries += ["z"]

    libgambatte_include_dirs = [
        "gambatte-core/common",
        "gambatte-core/libgambatte/src",
        "gambatte-core/libgambatte/include",
    ]

    gambatte_extension = Extension(
        "gambaterm.libgambatte",
        language="c++",
        include_dirs=[
            *libgambatte_include_dirs,
            "libgambatte_ext",
            numpy.get_include(),
        ],
        extra_compile_args=["-DHAVE_STDINT_H", "-DREVISION=0"],
        libraries=libraries,
        sources=[
            *libgambatte_sources,
            "libgambatte_ext/libgambatte.pyx",
        ],
    )

    termblit_extension = Extension(
        "gambaterm.termblit",
        language="c",
        include_dirs=[numpy.get_include()],
        sources=["termblit_ext/termblit.pyx"],
    )

    sextblit_extension = Extension(
        "gambaterm.sextblit",
        language="c",
        include_dirs=[numpy.get_include()],
        sources=["termblit_ext/sextblit.pyx"],
    )

    octblit_extension = Extension(
        "gambaterm.octblit",
        language="c",
        include_dirs=[numpy.get_include()],
        sources=["termblit_ext/octblit.pyx"],
    )

    halfblit_extension = Extension(
        "gambaterm.halfblit",
        language="c",
        include_dirs=[numpy.get_include()],
        sources=["termblit_ext/halfblit.pyx"],
    )

    return [
        gambatte_extension,
        termblit_extension,
        sextblit_extension,
        octblit_extension,
        halfblit_extension,
    ]


setup(ext_modules=get_extensions())
