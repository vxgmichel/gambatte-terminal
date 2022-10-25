import os
import sys
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
    if interactive:
        assert result.stderr == ""
        assert "| test_rom.gb |" in result.stdout
    else:
        assert result.stderr == "Warning: Input is not a terminal (fd=0).\n"
    if sys.platform == "linux":
        assert "▀ ▄▄ ▀" in result.stdout


def test_gambaterm_ssh(ssh_config: Path) -> None:
    assert TEST_ROM.exists()
    command = f"gambaterm-ssh {TEST_ROM} --break-after 10 --input-file /dev/null --color-mode 4"
    server = Popen(command.split(), stdout=PIPE, stderr=PIPE, bufsize=0, text=True)
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
