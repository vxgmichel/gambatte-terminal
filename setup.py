from __future__ import annotations

import glob
from pathlib import Path
from setuptools import Extension, setup


def get_extensions() -> list[Extension]:
    import numpy  # Lazy import; numpy provided via build-system requires

    # Gather all C++ sources (including file_zip.cpp for ZIP support)
    # Exclude file.cpp since file_zip.cpp provides the full implementation
    libgambatte_sources = [
        p
        for p in glob.glob("libgambatte/**/*.cpp", recursive=True)
        if not p.endswith("file.cpp")
    ]

    # Add minizip C sources for ZIP support
    minizip_sources = glob.glob("libgambatte/src/file/unzip/*.c", recursive=True)

    # Include dirs: parents of all headers
    include_dirs = list(
        {str(Path(h).parent) for h in glob.glob("libgambatte/**/*.h", recursive=True)}
    )

    gambatte_extension = Extension(
        "gambaterm.libgambatte",
        language="c++",
        include_dirs=[*include_dirs, "libgambatte_ext", numpy.get_include()],
        extra_compile_args=["-DHAVE_STDINT_H"],
        libraries=["z"],  # Link against zlib for ZIP support
        sources=[
            *libgambatte_sources,
            *minizip_sources,
            "libgambatte_ext/libgambatte.pyx",
        ],
    )

    termblit_extension = Extension(
        "gambaterm.termblit",
        language="c",
        include_dirs=[numpy.get_include()],
        sources=["termblit_ext/termblit.pyx"],
    )

    return [gambatte_extension, termblit_extension]


setup(ext_modules=get_extensions())
