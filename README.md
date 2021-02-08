gambatte-terminal
-----------------

A terminal front-end for gambatte, the gameboy color emulator.

![](demo.gif)


It supports:
- 16 colors, 256 colors and 24-bit colors terminal
- Playing audio from the emulator
- Using TAS input files as game input
- Using keyboard presses as game input

Installation
------------

Wheels are available on linux, windows and osx for python 3.6, 3.7, 3.8 and 3.9:

```shell
$ pip3 install gambaterm
```

Usage and arguments
-------------------

Usage:
```
usage: gambaterm [-h] [--input-file INPUT_FILE] [--frame-advance FRAME_ADVANCE] [--break-after BREAK_AFTER] [--speed-factor SPEED_FACTOR] [--force-gameboy]
                 [--skip-inputs SKIP_INPUTS] [--cpr-sync] [--disable-audio] [--color-mode COLOR_MODE]
                 ROM
```
Positional arguments:
 - `ROM`
                        Path to a GB or GBC rom file

Optional arguments:
  - `--input-file INPUT_FILE, -i INPUT_FILE`
                        Path to a bizhawk BK2 input file
  - `--frame-advance FRAME_ADVANCE, --fa FRAME_ADVANCE`
                        Number of frames to run before displaying the next one (default is 1)
  - `--break-after BREAK_AFTER, --ba BREAK_AFTER`
                        Number of frames to run before forcing the emulator to stop (doesn't stop by default)
  - `--speed-factor SPEED_FACTOR, --sf SPEED_FACTOR`
                        Speed factor to apply to the emulation (default is 1.0 corresponding to 60 FPS)
  - `--force-gameboy, --fg`
                        Force the emulator to treat the rom as a GB file
  - `--skip-inputs SKIP_INPUTS, --si SKIP_INPUTS`
                        Number of frame inputs to skip in order to compensate for the lack of BIOS (default is 188)
  - `--cpr-sync, --cs`
                        Use CPR synchronization to prevent video buffering
  - `--disable-audio, --da`
                        Disable audio entirely
  - `--color-mode COLOR_MODE, -c COLOR_MODE`
                        Force a color mode (1: 4 greyscale colors, 2: 16 colors, 3: 256 colors, 4: 24-bit colors)

SSH server
----------

It is possible to serve the emulation though SSH, although clients won't be able to send input to the emulator without an X server and the `ssh -X` option.

Use `gambaterm-ssh --help` for more information.


Terminal support
----------------

Not all terminals will actually offer a pleasant experience. The main criteria are:

- **Support for basic ANSI codes (VT100)**
  More specifically setting background/foreground colors and moving cursor (absolute and relative).
  Those are usually supported.

- **Support for at least 256 colors**
  Those are usually supported.
  16 colors also works but it doesn't look too good.
  In this case, it might be better to use greyscale colors using `--force-gameboy` or `--color-mode=1`.

- **Support for UTF-8 and good rendering of unicode block elements**
  More specifically the following characters "▄█▀".
  Changing the code page might be necessary on windows, using `chcp 65001`.
  Also, the alignement might be off (e.g small spaces between pixels)
  This is not always well supported.

- **Good rendering performance**
  The terminal has to be able to process about 500KB of requests per seconds for a smooth rendering of "intense" frames.
  Typically, the most intense frames happen during screen transitions of two detailed scenes.

The table below sums up my findings when I tried a the most common terminal emulators:

| Linux            | Status     | Colors        | Unicode rendering      | Performance | Comments                 |
|------------------|------------|---------------|------------------------|-------------|--------------------------|
| Gnome terminal   | Excellent  | 24-bit colors | Good                   | 60 FPS      |                          |
| Terminator       | Excellent  | 24-bit colors | Good                   | 60 FPS      |                          |
| Kitty            | Excellent  | 24-bit colors | Good                   | 60 FPS      |                          |
| XTerm            | Good       | 24-bit colors | Good                   | 60 FPS      | No resize shortcuts      |
| Termit           | Ok         | 24-bit colors | Good                   | 60 FPS      | No window title          |
| Rxvt             | Ok         | 256 colors    | Good                   | 60 FPS      | No resize shortcuts      |
| Mlterm           | Ok         | 24-bit colors | Light misalignments    | 60 FPS      | No resize shortcuts      |
| Terminology      | Ok         | 24-bit colors | Possible misalignments | 30 FPS      | Weird colors             |

| OSX              | Status     | Colors        | Unicode rendering      | Performance | Comments                 |
|------------------|------------|---------------|------------------------|-------------|--------------------------|
| iTerm2           | Good       | 24-bit colors | Good                   | 30 FPS      |                          |
| Terminal         | Unplayable | 256 colors    | Misalignments          | 20 FPS      |                          |

| Windows          | Status     | Colors        | Unicode rendering      | Performance | Comments                 |
|------------------|------------|---------------|------------------------|-------------|--------------------------|
| Windows terminal | Unpleasant | 24-bit colors | Good (`chcp 65001`)    | 30 FPS      | Buggy display            |
| Cmder            | Unplayable | 24-bit colors | Good (`chcp 65001`)    | 2 FPS       | No window title          |
| Terminus         | Unplayable | 24-bit colors | Misalignments          | 10 FPS      |                          |
| Command prompt   | Broken     | N/A           | N/A                    | N/A         | No ANSI code support     |
| Git bash         | Broken     | N/A           | N/A                    | N/A         | Doesn't work with winpty |


Keyboard input
--------------

The key bindings are not configurable at the moment:

| Buttons    | Keyboard     |
|------------|--------------|
| Directions | Arrows       |
| A          | F/V/Space    |
| B          | D/C/Alt      |
| Start      | Ctrl/Enter   |
| Select     | Shift/Delete |

Key releases cannot be detected through stdin, which is usually mandatory to play games. It is then required to access the window system to get access to the key presses. There are a couple of problems with that:

- It can be hard to detect the window corresponding to the terminal. With X11, the best solution is to look for the current focused window. For other systems, the fallback solution is to use global hotkeys.

- It only works through SSH for clients with X servers using `ssh -X`, meaning it requires Requires and MacOS users to run an X server. Moreover, it's a bad idea to connect with `-X` to an untrusted server.


Motivation
----------

To be honest, there is no actual reason to use this gameboy emulator, other than you might find it fun or interesting. The motivation behind this project is simply to push the idea of running a video game console emulator in a terminal as far as possible. It seems like there has been a [similar attempt](https://github.com/gabrielrcouto/php-terminal-gameboy-emulator) that used a different approach for displaying the video stream. In any case I'm quite satisfied with this project, and also a bit surprised that I could push it to the point where playing games it's actually enjoyable. In particular, I've been able to complete [The Bouncing Ball](https://gbhh.avivace.com/game/The-Bouncing-Ball) at 60 FPS in XTerm, which makes me want to try other homebrew games :)



Dependencies
------------

Here is the list of the dependencies used in this project, all great open source libraries:

- [gambatte](https://github.com/sinamas/gambatte) - Gameboy emulation
- [Cython](https://cython.org/) - Binding to gambatte C++ API, and fast video frame conversion
- [prompt-toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) - Handling of the terminal stream
- [samplerate](https://github.com/tuxu/python-samplerate) - Resampling the emulator audio stream
- [sounddevice](https://github.com/spatialaudio/python-sounddevice) - Playing the audio stream
- [xlib](https://github.com/python-xlib/python-xlib)/[pynput](https://github.com/moses-palmer/pynput) - Getting keyboard input
- [asyncssh](https://github.com/ronf/asyncssh) - Running the SSH server


Contact
-------

[Vincent Michel](mailto:vxgmichel@gmail.com)
