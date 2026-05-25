import os
import signal
import sys
import asyncio
import pytest
import asyncssh
from pathlib import Path
from typing import Iterator
from subprocess import Popen, PIPE, run

TEST_ROM = Path(__file__).parent / "test_rom.gb"

# Color argument variants for parametrization:
#   "forced"  -- explicit --color-mode 4, bypasses auto-detection
#   "auto"    -- no --color-mode, exercises detect_local_color_mode
COLOR_ARG_VARIANTS = (
    pytest.param("--color-mode 4", id="forced-color"),
    pytest.param("", id="auto-color"),
)


@pytest.fixture
def ssh_config(tmp_path: Path) -> Iterator[Path]:
    rsa_key = asyncssh.generate_private_key("ssh-rsa")
    (tmp_path / "id_rsa").write_bytes(rsa_key.export_private_key())
    (tmp_path / "id_rsa.pub").write_bytes(rsa_key.export_public_key())
    os.chmod(tmp_path / "id_rsa", 0o600)
    os.chmod(tmp_path / "id_rsa.pub", 0o600)
    os.environ["GAMBATERM_USER_SSH_DIR"] = str(tmp_path)
    yield tmp_path
    del os.environ["GAMBATERM_USER_SSH_DIR"]


@pytest.fixture
def gambaterm_config(tmp_path: Path) -> Iterator[Path]:
    os.environ["GAMBATERM_CONFIG_DIR"] = str(tmp_path)
    yield tmp_path
    del os.environ["GAMBATERM_CONFIG_DIR"]


@pytest.mark.parametrize("color_arg", COLOR_ARG_VARIANTS)
@pytest.mark.parametrize(
    "interactive", (False, True), ids=("non-interactive", "interactive")
)
def test_gambaterm(interactive: bool, color_arg: str) -> None:
    assert TEST_ROM.exists()
    command = (
        f"gambaterm {TEST_ROM} --break-after 10"
        f" --input-file /dev/null --disable-audio"
        + (f" {color_arg}" if color_arg else "")
    )
    result = run(
        f"script -e -q -c '{command}' /dev/null" if interactive else command,
        shell=True,
        check=True,
        text=True,
        capture_output=True,
    )
    assert result.stderr == ""
    if interactive:
        assert "| test_rom.gb |" in result.stdout
    if sys.platform == "linux":
        assert "▀ ▄▄ ▀" in result.stdout


@pytest.mark.parametrize("color_arg", COLOR_ARG_VARIANTS)
def test_gambaterm_ssh(
    ssh_config: Path, gambaterm_config: Path, color_arg: str
) -> None:
    assert TEST_ROM.exists()
    command = f"gambaterm-ssh {TEST_ROM} --break-after 10 --input-file /dev/null" + (
        f" {color_arg}" if color_arg else ""
    )
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    server = Popen(
        command.split(), stdout=PIPE, stderr=PIPE, bufsize=0, text=True, env=env
    )
    assert server.stdout is not None
    assert server.stderr is not None
    try:
        assert (
            server.stdout.readline()
            == f"Generating SSH host key at {gambaterm_config / 'ssh_host_key'}...\n"
        )
        assert server.stdout.readline() == "Authentication methods:\n"
        assert (
            server.stdout.readline()
            == f"- Public keys from: {ssh_config / 'id_rsa.pub'}\n"
        )
        assert server.stdout.readline() == "Running SSH server on 127.0.0.1:8022...\n"
        assert (gambaterm_config / "ssh_host_key").exists()

        async def ssh_client() -> str:
            async with asyncssh.connect(
                host="127.0.0.1",
                port=8022,
                client_keys=[str(ssh_config / "id_rsa")],
                known_hosts=None,
                username=os.environ.get("USER", "user"),
            ) as conn:
                result = await conn.run(
                    "",
                    term_type="xterm-256color",
                    term_size=(80, 24),
                )
                assert isinstance(result.stdout, str)
                return result.stdout

        client_stdout = asyncio.run(ssh_client())
        assert "| test_rom.gb |" in client_stdout
        assert "▀ ▄▄ ▀" in client_stdout
    finally:
        server.send_signal(signal.SIGINT)
        server.wait()
        print(server.stdout.read(), end="", file=sys.stdout)
        print(server.stderr.read(), end="", file=sys.stderr)
        server.stdout.close()
        server.stderr.close()
        assert server.returncode == 0


@pytest.mark.parametrize("color_arg", COLOR_ARG_VARIANTS)
def test_gambaterm_telnet(color_arg: str) -> None:
    assert TEST_ROM.exists()
    command = (
        f"{sys.executable} -m gambaterm.telnet {TEST_ROM} --break-after 10"
        f" --input-file /dev/null" + (f" {color_arg}" if color_arg else "")
    )
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    server = Popen(
        command.split(), stdout=PIPE, stderr=PIPE, bufsize=0, text=True, env=env
    )
    assert server.stdout is not None
    assert server.stderr is not None
    try:
        assert (
            server.stdout.readline() == "Running telnet server on 127.0.0.1:8023...\n"
        )

        async def telnet_client() -> str:
            import telnetlib3

            reader, writer = await telnetlib3.open_connection(
                host="127.0.0.1",
                port=8023,
                encoding=False,
                force_binary=True,
                term="xterm-256color",
                cols=80,
                rows=24,
            )
            output = b""
            try:
                while True:
                    chunk = await asyncio.wait_for(reader.read(65536), timeout=5)
                    if not chunk:
                        break
                    if isinstance(chunk, bytes):
                        output += chunk
            except (asyncio.TimeoutError, EOFError):
                pass
            finally:
                if not writer.is_closing():
                    writer.close()
            return output.decode("utf-8", errors="replace")

        result = asyncio.run(telnet_client())
        assert "| test_rom.gb |" in result
        assert "\u2580" in result or "\u2584" in result
    finally:
        server.send_signal(signal.SIGINT)
        server.wait()
        print(server.stdout.read(), end="", file=sys.stdout)
        print(server.stderr.read(), end="", file=sys.stderr)
        server.stdout.close()
        server.stderr.close()
        assert server.returncode == 0


def test_gambaterm_telnet_unknown_term() -> None:
    """Telnet client connects with an unknown terminal type.

    Exercises the ``kind=None`` fallback path in RemoteTerminal, where blessed's
    ``__init_termcap_kind`` resolves the terminal type through protocol-negotiated TERM and
    fallsback to ``kind_fallback='xterm-256color'``.
    """
    assert TEST_ROM.exists()
    command = (
        f"{sys.executable} -m gambaterm.telnet {TEST_ROM} --break-after 10"
        f" --input-file /dev/null"
    )
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    server = Popen(
        command.split(), stdout=PIPE, stderr=PIPE, bufsize=0, text=True, env=env
    )
    assert server.stdout is not None
    assert server.stderr is not None
    try:
        assert (
            server.stdout.readline() == "Running telnet server on 127.0.0.1:8023...\n"
        )

        async def telnet_client() -> str:
            import telnetlib3

            reader, writer = await telnetlib3.open_connection(
                host="127.0.0.1",
                port=8023,
                encoding=False,
                force_binary=True,
                term="unknown",
                cols=80,
                rows=24,
            )
            output = b""
            try:
                while True:
                    chunk = await asyncio.wait_for(reader.read(65536), timeout=5)
                    if not chunk:
                        break
                    if isinstance(chunk, bytes):
                        output += chunk
            except (asyncio.TimeoutError, EOFError):
                pass
            finally:
                if not writer.is_closing():
                    writer.close()
            return output.decode("utf-8", errors="replace")

        result = asyncio.run(telnet_client())
        assert "| test_rom.gb |" in result
        assert "\u2580" in result or "\u2584" in result
    finally:
        server.send_signal(signal.SIGINT)
        server.wait()
        print(server.stdout.read(), end="", file=sys.stdout)
        print(server.stderr.read(), end="", file=sys.stderr)
        server.stdout.close()
        server.stderr.close()
        assert server.returncode == 0
