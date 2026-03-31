gambatte-terminal
-----------------

[![](https://github.com/vxgmichel/gambatte-terminal/actions/workflows/build.yml/badge.svg)](https://github.com/vxgmichel/gambatte-terminal/actions/workflows/build.yml)
[![](https://img.shields.io/pypi/v/gambaterm.svg)](https://pypi.python.org/pypi/gambaterm)
[![](https://img.shields.io/pypi/pyversions/gambaterm.svg)](https://pypi.python.org/pypi/gambaterm)


A terminal front-end for gambatte, the gameboy color emulator.

![](https://github.com/vxgmichel/gambatte-terminal/raw/main/demo.gif)


It supports:
- 16 colors, 256 colors and 24-bit colors terminal
- Playing audio from the emulator
- Using TAS input files as game input
- Using keyboard presses as game input


Quickstart
----------

Using [uvx](https://docs.astral.sh/uv/guides/tools/):

```shell
$ uvx gambaterm myrom.gbc
```


Installation
------------

Wheels are available on linux, windows and macos for python 3.10 to 3.14:

```shell
$ pip3 install gambaterm
```

Usage and arguments
-------------------

Usage:
```
usage: gambaterm [-h] [--input-file INPUT_FILE] [--frame-advance FRAME_ADVANCE]
                 [--break-after BREAK_AFTER] [--speed SPEED] [--force-gameboy]
                 [--skip-inputs SKIP_INPUTS] [--cpr-sync] [--disable-audio]
                 [--color-mode COLOR_MODE]
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

  - `--speed SPEED, -s SPEED`

    Control the execution speed (default is 1.0)

  - `--force-gameboy, --fg`

    Force the emulator to treat the rom as a GB file

  - `--skip-inputs SKIP_INPUTS, --si SKIP_INPUTS`

    Number of frame inputs to skip in order to compensate for the lack of BIOS (default is 188)

  - `--cpr-sync, --cs`

    Use CPR synchronization to prevent video buffering

  - `--enable-controller, --ec`

    Enable game controller support

  - `--disable-audio, --da`

    Disable audio entirely

  - `--color-mode COLOR_MODE, -c COLOR_MODE`

    Force a color mode (1: 4 greyscale colors, 2: 16 colors, 3: 256 colors, 4: 24-bit colors)
    Note: the color mode can be cycled at runtime by pressing the Tab key, which is useful for testing the different color modes supported by the terminal.


SSH server
----------

It is possible to serve the emulation through SSH. Clients with terminals supporting the [kitty keyboard protocol](https://sw.kovidgoyal.net/kitty/keyboard-protocol/) can send input directly without X11 forwarding. Otherwise, X11 forwarding (`ssh -X`) can be used as a fallback. Use `gambaterm-ssh --help` for more information. 24-bit color is always true over ssh.


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
  More specifically the following characters `▄ █ ▀`.
  Also, the alignement might be off (e.g small spaces between pixels)
  This is not always well supported.

- **Support for the [kitty keyboard protocol](https://sw.kovidgoyal.net/kitty/keyboard-protocol/)**
  This is mandatory if you're using Wayland, and recommended on every other platforms.
  In the case where the kitty keyboard protocol is not detected by `gambaterm`, the following fallbacks are implemented:
  * Linux: uses X11 through `python-xlib`
  * Macos: uses `pynput` (it requires granting specific authorizations to the terminal app)
  * Windows: uses `pynput` (the key presses are detected even if the terminal windows is not focused)
  It is also mandatory when connecting to a `gambaterm` SSH server.

- **Good rendering performance**
  The terminal has to be able to process about 500KB of requests per seconds for a smooth rendering of "intense" frames.
  Typically, the most intense bursts happen during screen transitions of two detailed scenes.

The table below sums up my findings when I tried the most common terminal emulators. Here's about linux:

| Linux            | Status     | Colors        | Unicode rendering      | Kitty keyboard protocol | Performance | Comments                                                    |
|------------------|------------|---------------|------------------------|-------------------------|-------------|-------------------------------------------------------------|
| Ghostty          | Excellent  | 24-bit colors | Good                   | Yes                     | 60 FPS      |                                                             |
| Kitty            | Excellent  | 24-bit colors | Good                   | Yes                     | 60 FPS      |                                                             |
| foot             | Excellent  | 24-bit colors | Good                   | Yes                     | 60 FPS      |                                                             |
| Alacritty        | Excellent  | 24-bit colors | Good                   | Yes                     | 60 FPS      |                                                             |
| Rio              | Excellent  | 24-bit colors | Good                   | Yes                     | 60 FPS      |                                                             |
| Konsole          | Good       | 24-bit colors | Good                   | No                      | 60 FPS      |                                                             |
| Gnome terminal   | Good       | 24-bit colors | Good                   | No                      | 60 FPS      |                                                             |
| Terminator       | Good       | 24-bit colors | Good                   | No                      | 60 FPS      |                                                             |
| XTerm            | Good       | 24-bit colors | Good                   | No                      | 60 FPS      | No resize shortcuts, launch as ``xterm -tn xterm-256color`` |
| Rxvt             | Good       | 24-bit colors | Good                   | No                      | 60 FPS      | No resize shortcuts                                         |
| Termit           | Ok         | 24-bit colors | Good                   | No                      | 60 FPS      | No window title                                             |
| Mlterm           | Ok         | 24-bit colors | Light misalignments    | No                      | 60 FPS      | No resize shortcuts                                         |
| Terminology      | Ok         | 24-bit colors | Possible misalignments | No                      | 30 FPS      | Weird colors                                                |
| Contour          | Bad        | 24-bit colors | Good                   | Broken                  | 60 FPS      | [Bug (no release event!)](https://github.com/contour-terminal/contour/pull/1924) |

About MacOS:

| MacOS            | Status     | Colors        | Unicode rendering         | Kitty keyboard protocol | Performance | Comments                 |
|------------------|------------|---------------|---------------------------|-------------------------|-------------|--------------------------|
| iTerm2           | Excellent  | 24-bit colors | Good                      | Yes                     | 60 FPS      |                          |
| Terminal         | Bad        | 24-bit colors | Bad--adjust font spacing! | No                      | 30 FPS      | A bit jittery            |

About Windows:

| Windows            | Status     | Colors        | Unicode rendering      | Kitty keyboard protocol | Performance | Comments                 |
|--------------------|------------|---------------|------------------------|-------------------------|-------------|--------------------------|
| Windows terminal   | Good       | 24-bit colors | Good                   | Coming Soon             | 60 FPS      | [Download Preview for kitty support)](https://github.com/microsoft/terminal/releases) |
| Cmder              | Unplayable | 24-bit colors | Good                   | Yes                     | 2 FPS       | No window title          |
| Terminus           | Unplayable | 24-bit colors | Misalignments          | No                      | 10 FPS      |                          |
| Command prompt     | Bad        | 24-bit colors | Good                   | No                      | 1 FPS       | Slow/Unresponsive        |
| Git bash (mingw64) | Ok         | 24-bit colors | Good                   | No                      | N/A         |                          |


Terminals without Kitty keyboard protocol require X11 to play locally, or X11 forwarding to use over SSH.

Terminal size
-------------

The emulator uses a single character on screen to display two vertically aligned pixels, like so `▄▀`. The gameboy being 160 pixels wide over 144 pixels high, you'll need your terminal to be at least 160 characters wide over 72 characters high to display the entire screen. Setting the terminal to full screen is usually enough but you might want to tweak the character size, typically using the `ctrl - / ctrl +` or `ctrl wheel` shortcuts.

Keyboard, game controller and file inputs
-----------------------------------------

Keyboard controls are enabled by default, while game controller controls have to be enabled using `--enable-controller` or `--ec`.

The key bindings are not configurable at the moment:

| Buttons    | Keyboard with arrows | Keyboard with WASD | Controller            |
|------------|----------------------|--------------------|-----------------------|
| Directions | Arrows               | W A S D            | Left hat / Left stick |
| A          | X                    | K                  | Button 0 / Button 3   |
| B          | Z                    | J                  | Button 1 / Button 2   |
| Start      | Enter                | Enter              | Button 7              |
| Select     | Right Shift          | Right Shift        | Button 6              |


| Save state commands | Keyboard |
|---------------------|----------|
| Select slot         | 0 to 9   |
| Save state          | `[`      |
| Load state          | `]`      |


Since `gambaterm` detects physical key presses, this table indicates the keys [as seen on a QWERTY keyboard](https://www.w3.org/TR/uievents-code/#key-alphanumeric-writing-system). In particular, AZERTY or Bépo user won't need to change their keyboard layout in order to play.
It is also possible to use a bizhawk BK2 input file to play tool-assisted speedruns using the `--input-file` (or `-i`) option.


Motivation
----------

To be honest there is no actual reason to use this gameboy emulator, other than you might find it fun or interesting. The motivation behind this project is simply to push the idea of running a video game console emulator in a terminal as far as possible. It seems like there has been a [similar attempt](https://github.com/gabrielrcouto/php-terminal-gameboy-emulator) that used a different approach for displaying the video stream. In any case I'm quite satisfied with this project, and also a bit surprised that I could push it to the point where playing games is actually enjoyable. In particular, I've been able to complete [The Bouncing Ball](https://hh.gbdev.io/game/the-bouncing-ball) at 60 FPS in XTerm, and I'm now looking forward to playing more homebrew games :)



Dependencies
------------

Here is the list of the dependencies used in this project, all great open source libraries:

- [gambatte-core](https://github.com/pokemon-speedrunning/gambatte-core) - Gameboy emulation
- [Cython](https://cython.org/) - Binding to gambatte C++ API, and fast video frame conversion
- [blessed](https://github.com/jquast/blessed) - Cross-platform terminal handling and kitty keyboard protocol support
- [samplerate](https://github.com/tuxu/python-samplerate) - Resampling the audio stream
- [sounddevice](https://github.com/spatialaudio/python-sounddevice) - Playing the audio stream
- [xlib](https://github.com/python-xlib/python-xlib)/[pynput](https://github.com/moses-palmer/pynput) - Getting keyboard inputs
- [pygame](https://github.com/pygame/pygame) - Getting game controller inputs
- [asyncssh](https://github.com/ronf/asyncssh) - Running the SSH server


Contact
-------

[Vincent Michel](mailto:vxgmichel@gmail.com)
