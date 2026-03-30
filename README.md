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
usage: gambaterm [-h] [--input-file INPUT_FILE] [--frame-advance FRAME_ADVANCE] [--break-after BREAK_AFTER] [--speed-factor SPEED_FACTOR] [--force-gameboy]
                 [--skip-inputs SKIP_INPUTS] [--cpr-sync] [--disable-audio] [--color-mode COLOR_MODE] [--no-sextants] [--no-octants]
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

  - `--enable-controller, --ec`

    Enable game controller support

  - `--disable-audio, --da`

    Disable audio entirely

  - `--color-mode COLOR_MODE, -c COLOR_MODE`

    Force a color mode (1: 4 greyscale colors, 2: 16 colors, 3: 256 colors, 4: 24-bit colors)

  - `--no-sextants`

    Disable sextant block rendering

  - `--no-octants`

    Disable octant block rendering, Octant blocks requires Unicode 17.0 or newer font

SSH server
----------

It is possible to serve the emulation though SSH, although clients won't be able to send input to the emulator without an X server and the `ssh -X` option. Use `gambaterm-ssh --help` for more information.


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
  More specifically the half-block characters `▄ █ ▀` for terminals sizes 160x72 or larger.

  For smaller terminal sizes, Unicode 13.0 (2020) Sextant (🬴) and Unicode 16.0 (2024) Octant (𜷠)
  are used but provide lower color fidelity and undesirable effects for horizontal and vertical
  scrolling.

  Also, the alignment might be off (e.g small spaces between pixels), such as in Mac OSX
  Terminal.app, and can be adjusted by vertical and horizontal spacing of font preferences.

- **Support for the [kitty keyboard protocol](https://sw.kovidgoyal.net/kitty/keyboard-protocol/)**
  This is mandatory if you're using Wayland, and recomended on every other platforms.
  In the case where the kitty keyboard protocol is not detected by `gambaterm`, the following fallbacks are implemented:
  * Linux: uses X11 through `python-xlib`
  * Macos: uses `pynput` (it requires granting specific authorizations to the terminal app)
  * Windows: uses `pynput` (the key presses are detected even if the terminal windows is not focused)
  It is also mandatory when connecting to a `gambaterm` SSH server.

- **Good rendering performance**
  The terminal has to be able to process about 500KB of requests per seconds for a smooth rendering of "intense" frames.
  Typically, the most intense bursts happen during screen transitions of two detailed scenes.

The table below sums up my findings when I tried a the most common terminal emulators. Here's about linux:

| Linux            | Status     | Colors        | Unicode rendering      | Kitty keyboard protocol | Performance | Comments                 |
|------------------|------------|---------------|------------------------|-------------------------|-------------|--------------------------|
| Ghostty          | Excellent  | 24-bit colors | Good                   | Yes                     | 60 FPS      |                          |
| Kitty            | Excellent  | 24-bit colors | Good                   | Yes                     | 60 FPS      |                          |
| Gnome terminal   | Good       | 24-bit colors | Good                   | No                      | 60 FPS      |                          |
| Terminator       | Good       | 24-bit colors | Good                   | No                      | 60 FPS      |                          |
| XTerm            | Good       | 24-bit colors | Good                   | No                      | 60 FPS      | No resize shortcuts      |
| Termit           | Ok         | 24-bit colors | Good                   | No                      | 60 FPS      | No window title          |
| Rxvt             | Ok         | 256 colors    | Good                   | No                      | 60 FPS      | No resize shortcuts      |
| Mlterm           | Ok         | 24-bit colors | Light misalignments    | No                      | 60 FPS      | No resize shortcuts      |
| Terminology      | Ok         | 24-bit colors | Possible misalignments | No                      | 30 FPS      | Weird colors             |

About MacOS:

| MacOS            | Status     | Colors        | Unicode rendering      | Kitty keyboard protocol | Performance | Comments                 |
|------------------|------------|---------------|------------------------|-------------------------|-------------|--------------------------|
| iTerm2           | Good       | 24-bit colors | Good                   | Yes                     | 30 FPS      |                          |
| Terminal         | Unplayable | 256 colors    | Misalignments          | No                      | 20 FPS      |                          |

About Windows:

| Windows          | Status     | Colors        | Unicode rendering      | Kitty keyboard protocol | Performance | Comments                 |
|------------------|------------|---------------|------------------------|-------------------------|-------------|--------------------------|
| Windows terminal | Good       | 24-bit colors | Good                   | Soon                    | 60 FPS      |                          |
| Cmder            | Unplayable | 24-bit colors | Good                   | Yes                     | 2 FPS       | No window title          |
| Terminus         | Unplayable | 24-bit colors | Misalignments          | No                      | 10 FPS      |                          |
| Command prompt   | Broken     | N/A           | N/A                    | No                      | N/A         | No ANSI code support     |
| Git bash         | Broken     | N/A           | N/A                    | No                      | N/A         | Doesn't work with winpty |

Terminal size
-------------

The Game Boy display is 160x144 pixels. The emulator automatically selects the best rendering mode based on the terminal size:

| Mode | Characters | Terminal size | Pixels per cell |
|------|-----------|---------------|-----------------|
| Half-blocks | `▄ █ ▀` | 160+ cols, 72+ rows | 1x2 |
| Sextants | U+1FB00 | 80+ cols, 48+ rows | 2x3 |
| Octants | U+1CD00 | below 80x48 | 2x4 |

- **Half-blocks** render the full 160-column image at its native horizontal resolution. This requires a wide terminal (160+ columns) and at least 72 rows.
- **Sextants** pack 2x3 pixels into each character cell, halving the required width to 80 columns and needing 48 rows. This mode is auto-selected when the terminal is narrower than 160 columns.
- **Octants** pack 2x4 pixels per cell, requiring only 80 columns and 36 rows. This mode is auto-selected when the terminal has fewer than 48 rows. Octant characters are part of Unicode 16.0 and require a supporting font (e.g. GNU Unifont 16.0+).

Both Sextants and Octants compromise color fidelity as only 2 colors per terminal cell of 2x3 or
2x4 pixel block can be selected. This can also cause undesirable artifacts especially during
horizontal and vertical scroll.

Unicode 16.0 Octants (2024) (𜷠) are relatively new, and may display as "tofu symbol" or "empty box"
instead of the desired octant, and not yet frequently supported, and may require installation of a
newer font, such as GNU Unifont 16.0 or newer https://unifoundry.com/unifont/index.html

The mode is re-evaluated on terminal resize, so shrinking or growing the window switches modes
dynamically. Use `--no-sextants` or `--no-octants` to disable mode.

Setting the terminal to full screen is usually enough but you might want to tweak the character size, typically using the `ctrl - / ctrl +` or `ctrl wheel` shortcuts.

Keyboard, game controller and file inputs
-----------------------------------------

Keyboard controls are enabled by default, while game controller controls have to be enabled using `--enable-controller` or `--ec`.

The key bindings are not configurable at the moment:

| Buttons    | Keyboard with arrows | Keyboard with WASD | Controller            |
|------------|----------------------|--------------------|-----------------------|
| Directions | Arrows               | W A S D            | Left hat / Left stick |
| A          | Z                    | K                  | Button 0 / Button 3   |
| B          | X                    | J                  | Button 1 / Button 2   |
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

To be honest there is no actual reason to use this gameboy emulator, other than you might find it fun or interesting. The motivation behind this project is simply to push the idea of running a video game console emulator in a terminal as far as possible. It seems like there has been a [similar attempt](https://github.com/gabrielrcouto/php-terminal-gameboy-emulator) that used a different approach for displaying the video stream. In any case I'm quite satisfied with this project, and also a bit surprised that I could push it to the point where playing games is actually enjoyable. In particular, I've been able to complete [The Bouncing Ball](https://gbhh.avivace.com/game/The-Bouncing-Ball) at 60 FPS in XTerm, and I'm now looking forward to playing more homebrew games :)



Dependencies
------------

Here is the list of the dependencies used in this project, all great open source libraries:

- [gambatte-core](https://github.com/pokemon-speedrunning/gambatte-core) - Gameboy emulation
- [Cython](https://cython.org/) - Binding to gambatte C++ API, and fast video frame conversion
- [prompt-toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) - Cross-platform terminal handling
- [samplerate](https://github.com/tuxu/python-samplerate) - Resampling the audio stream
- [sounddevice](https://github.com/spatialaudio/python-sounddevice) - Playing the audio stream
- [xlib](https://github.com/python-xlib/python-xlib)/[pynput](https://github.com/moses-palmer/pynput) - Getting keyboard inputs
- [pygame](https://github.com/pygame/pygame) - Getting game controller inputs
- [asyncssh](https://github.com/ronf/asyncssh) - Running the SSH server


Contact
-------

[Vincent Michel](mailto:vxgmichel@gmail.com)
