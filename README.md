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
usage: gambaterm [-h] [--input-file INPUT_FILE] [--color-mode COLOR_MODE]
                 [--frame-advance FRAME_ADVANCE] [--break-after BREAK_AFTER]
                 [--speed SPEED] [--skip-inputs SKIP_INPUTS] [--cpr-sync]
                 [--enable-controller] [--write-input WRITE_INPUT]
                 [--no-sextants] [--octants] [--cp437] [--force-gameboy]
                 [--save-directory SAVE_DIRECTORY] [--disable-audio]
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


  - `--no-sextants`

    Disable sextant block rendering

  - `--octants`

    Enable octant block rendering, requires a Unicode 16.0 or newer font. Toggle at runtime with Ctrl+O.

  - `--cp437`

    Restrict to CP437 block characters only (▀ ▄ █ ▌ ▐), disabling sextants, octants, and
    eighth-height blocks. Toggle at runtime with Ctrl+P.

  - `--write-input WRITE_INPUT, --wi WRITE_INPUT`

    Record inputs into a file

  - `--save-directory SAVE_DIRECTORY, --sd SAVE_DIRECTORY`

    Path to the save directory

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
  More specifically the half-block characters `▄ █ ▀` for terminals sizes 160x72 or larger.

  For smaller terminal sizes, Unicode 13.0 (2020) Sextant (🬴) characters are used automatically,
  and Unicode 16.0 (2024) Octant (𜷠) characters can be enabled with `--octants` or by toggled
  by pressing ``Ctrl + O`` in the lowest resolution, providing very comparable quality..

  Octant rendering requires a font with glyphs in the U+1CD00 plane. [GNU
  Unifont](https://unifoundry.com/unifont/) provides full coverage by installing **both** files:

  - unifont-XX.X.XX.otf - Basic Multilingual Plane
  - unifont_upper-XX.X.XX.otf - Supplementary planes

  Also, the alignment might be off (e.g small spaces between pixels), such as in Mac OSX
  Terminal.app, and can be adjusted by vertical and horizontal spacing of font preferences.

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

The Game Boy display is 160x144 pixels. The emulator automatically selects the best rendering mode based on the terminal size:

| Mode | Characters | Terminal size | Pixels per cell |
|------|-----------|---------------|-----------------|
| Full-res half-blocks | `▄ █ ▀` | 160+ cols, 72+ rows | 1×2 |
| Sextants | U+1FB00 (64 chars) | 80+ cols, 48+ rows | 2×3 |
| Half-res half-blocks | `▂ ▄ ▆ ▌ ▐` + U+1FB82/85 | below 80×48 | 2×4 |
| Octants (opt-in) | U+1CD00 (256 chars) | below 80×48 | 2×4 |

- **Full-res half-blocks** render the full 160-column image at its native horizontal resolution.
  Each terminal cell maps to 2 vertically stacked pixels using `▀` (upper half) and `▄` (lower
  half). This requires a wide terminal (160+ columns) and at least 72 rows.

- **Sextants** pack 2×3 pixels into each character cell, halving the required width to 80 columns
  and needing 48 rows. The best 2-color pair is selected per cell and mapped to one of 64 sextant
  characters (U+1FB00–U+1FB3B). This mode is auto-selected when the terminal is narrower than
  160 columns. Sextant characters have been widely supported since Unicode 13.0 (2020).

- **Half-res half-blocks** are the default fallback for terminals below 80×48. Each cell covers a
  2×4 pixel region (same grid as octants) but uses widely-supported block elements instead of
  Unicode 16.0 characters. The blitter analyzes all 8 pixels per cell, finds the best 2-color
  pair, then scores horizontal splits at 1/4, 1/2, and 3/4 boundaries and a vertical left/right
  split, picking whichever has the fewest mismatched pixels:

  - Horizontal: `▂` (lower 2/8), `▄` (lower 4/8), `▆` (lower 6/8), and their upper
    counterparts U+1FB82 (upper 2/8) and U+1FB85 (upper 6/8)
  - Vertical: `▌` (left half), `▐` (right half)

  This gives 4 smooth vertical scroll steps per cell instead of 2, and correctly renders
  vertical strokes that would otherwise be lost in a horizontal-only downscale. All characters
  used are from Unicode 1.0 (U+2580–U+259F) except U+1FB82 and U+1FB85 which are from
  Unicode 13.0 — both universally supported.

- **Octants** pack 2×4 pixels per cell with 256 possible binary patterns, providing the highest
  spatial fidelity of the reduced modes. Enabled with `--octants` or Ctrl+O at runtime. Octant
  characters are part of Unicode 16.0 (2024) and require a supporting font. See the font
  installation section above.

All reduced-resolution modes (sextant, half-res, octant) are limited to 2 colors per cell.
Content with 3 or more colors in a single cell is quantized to the best 2-color pair, which can
cause color oscillation during scrolling. A per-cell hysteresis cache dampens this by snapping to
previously rendered colors when the new pair is perceptually close. A per-cell hysteresis cache dampens this by snapping to previously rendered
colors when the new pair is perceptually close.

The mode is re-evaluated on terminal resize, so shrinking or growing the window switches modes
dynamically. Use `--no-sextants` to disable sextant mode, `--octants` to enable octants.

Setting the terminal to full screen is usually enough but you might want to tweak the character size, typically using the `ctrl - / ctrl +` or `ctrl wheel` shortcuts.

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
