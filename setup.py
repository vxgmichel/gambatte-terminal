import os
import glob
from setuptools import Extension, setup

# List libgambatte sources, excluding `file_zip.cpp`
libgambatte_sources = glob.glob("libgambatte/**/*.cpp", recursive=True)
libgambatte_sources.remove("libgambatte/src/file/file_zip.cpp")

# List all directories containing `.h` files
include_dirs = list(
    set(
        f"-I{os.path.dirname(path)}"
        for path in glob.glob("libgambatte/**/*.h", recursive=True)
    )
)

# The gambatte extension, including libgambatte with the Cython wrapper
gambatte_extension = Extension(
    "gambaterm._gambatte",
    language="c++",
    extra_compile_args=include_dirs + ["-DHAVE_STDINT_H"],
    sources=libgambatte_sources + ["ext/_gambatte.pyx"],
)


setup(
    name="gambaterm",
    version="0.1.0",
    packages=["gambaterm"],
    setup_requires=["setuptools>=18.0", "cython", "numpy"],
    ext_modules=[gambatte_extension],
    install_requires=[
        "numpy",
        "asyncssh",
        "sounddevice",
        "samplerate",
        "xlib; sys_platform == 'linux'",
    ],
    tests_require=["pytest"],
    python_requires=">=3.6",
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
