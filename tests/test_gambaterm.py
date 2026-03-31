import os
import sys
import asyncio
import pytest
import asyncssh
from pathlib import Path
from typing import Iterator
from subprocess import Popen, PIPE, run

TEST_ROM = Path(__file__).parent / "test_rom.gb"


@pytest.fixture
def ssh_config(tmp_path: Path) -> Iterator[Path]:
    rsa_key = asyncssh.generate_private_key("ssh-rsa")
    (tmp_path / "id_rsa").write_bytes(rsa_key.export_private_key())
    (tmp_path / "id_rsa.pub").write_bytes(rsa_key.export_public_key())
    os.chmod(tmp_path / "id_rsa", 0o600)
    os.chmod(tmp_path / "id_rsa.pub", 0o600)
    os.environ["GAMBATERM_SSH_KEY_DIR"] = str(tmp_path)
    yield tmp_path
    del os.environ["GAMBATERM_SSH_KEY_DIR"]


@pytest.mark.parametrize(
    "interactive", (False, True), ids=("non-interactive", "interactive")
)
def test_gambaterm(interactive: bool) -> None:
    assert TEST_ROM.exists()
    command = f"gambaterm {TEST_ROM} --break-after 10 --input-file /dev/null --disable-audio --color-mode 4"
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


def test_gambaterm_ssh(ssh_config: Path) -> None:
    assert TEST_ROM.exists()
    command = f"gambaterm-ssh {TEST_ROM} --break-after 10 --input-file /dev/null --color-mode 4"
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    server = Popen(
        command.split(), stdout=PIPE, stderr=PIPE, bufsize=0, text=True, env=env
    )
    assert server.stdout is not None
    assert server.stderr is not None
    try:
        assert server.stdout.readline() == "Running ssh server on 127.0.0.1:8022...\n"
        client = run(
            f"ssh -tt -q localhost -p 8022 -X -i {ssh_config / 'id_rsa'} -o StrictHostKeyChecking=no",
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert client.stderr == ""
        assert "| test_rom.gb |" in client.stdout
        if sys.platform == "linux":
            assert "▀ ▄▄ ▀" in client.stdout
    finally:
        server.terminate()
        server.wait()
        print(server.stdout.read(), end="", file=sys.stdout)
        print(server.stderr.read(), end="", file=sys.stderr)
        server.stdout.close()
        server.stderr.close()


def test_gambaterm_telnet() -> None:
    assert TEST_ROM.exists()
    command = (
        f"{sys.executable} -m gambaterm.telnet {TEST_ROM} --break-after 10"
        f" --input-file /dev/null --color-mode 4"
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
        if sys.platform == "linux":
            assert "\u2580" in result or "\u2584" in result
    finally:
        server.terminate()
        server.wait()
        print(server.stdout.read(), end="", file=sys.stdout)
        print(server.stderr.read(), end="", file=sys.stderr)
        server.stdout.close()
        server.stderr.close()
