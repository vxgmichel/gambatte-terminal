import sys
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import gambaterm.telnet as gambaterm_telnet
from gambaterm.console import GameboyColor
from gambaterm.main import AppConfig
from gambaterm.remote_terminal import RemoteTerminal, KeyboardSupportDetection


rom = Path(sys.argv[1])


def test_frontend(
    terminal: RemoteTerminal,
    app_config: AppConfig,
    keyboard_support_detection: KeyboardSupportDetection,
) -> AppConfig:
    terminal.stream.write("TEST_FRONTEND_ACTIVE\n")
    terminal.stream.flush()
    return app_config


namespace = argparse.Namespace(
    romfile=rom,
    input_file=Path(sys.argv[2]),
    skip_inputs=188,
    color_mode=None,
    frame_advance=1,
    break_after=10,
    speed=1.0,
    cpr_sync=False,
    save_directory=None,
    force_gameboy=False,
)


async def main() -> None:
    with ThreadPoolExecutor(max_workers=4) as executor:
        async with gambaterm_telnet.run_telnet_server(
            bind="127.0.0.1",
            port=8023,
            robot_check=False,
            max_players=0,
            idle_timeout=None,
            console_cls=GameboyColor,
            namespace=namespace,
            users_directory=Path("."),
            executor=executor,
            frontend=test_frontend,
        ):
            await asyncio.Future()


try:
    asyncio.run(main())
except KeyboardInterrupt:
    pass
