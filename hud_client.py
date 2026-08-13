#!/usr/bin/env python3
"""HUD measurement software socket client.

Switch one or more configuration files and execute measurement commands.
"""

from __future__ import annotations

import argparse
import ast
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path


TERMINATOR = b"%"


class HudProtocolError(RuntimeError):
    """Raised when the HUD software returns an unexpected response."""


@dataclass(frozen=True)
class TestResult:
    config: str
    command: str
    response: str


class HudClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 5555, timeout: float = 60.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._socket: socket.socket | None = None
        self._buffer = bytearray()

    def connect(self) -> None:
        if self._socket is not None:
            return
        self._socket = socket.create_connection((self.host, self.port), self.timeout)
        self._socket.settimeout(self.timeout)

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        self._buffer.clear()

    def __enter__(self) -> "HudClient":
        self.connect()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def request(self, command: str) -> str:
        """Send one command and receive through the first '%' terminator."""
        if self._socket is None:
            raise RuntimeError("HUD client is not connected")

        wire_command = command.strip()
        if not wire_command:
            raise ValueError("Command cannot be empty")

        # Configuration commands are explicitly documented with a trailing '%'.
        # Other commands are documented without it, so preserve the caller's form.
        self._socket.sendall(wire_command.encode("utf-8"))
        return self._receive_message()

    def _receive_message(self) -> str:
        if self._socket is None:
            raise RuntimeError("HUD client is not connected")

        while True:
            end = self._buffer.find(TERMINATOR)
            if end >= 0:
                message = bytes(self._buffer[: end + 1])
                del self._buffer[: end + 1]
                return message.decode("utf-8", errors="replace").strip()

            chunk = self._socket.recv(4096)
            if not chunk:
                raise ConnectionError("HUD software closed the connection before returning '%'")
            self._buffer.extend(chunk)

    def camera_ready(self) -> bool:
        return self.request("gin") == "OK%"

    def switch_config(self, config_name: str) -> None:
        name = config_name.strip()
        if not name:
            raise ValueError("Configuration name cannot be empty")
        if name.lower().endswith(".ini"):
            name = name[:-4]

        response = self.request(f"c-{name}%")
        if response != "OK%":
            raise HudProtocolError(f"Failed to switch configuration {name!r}: {response}")

    def measure(self, command: str) -> str:
        response = self.request(command)
        expected_prefix = command.split("/", 1)[0] + "_Result"
        if response in {"Error0%", "Error1%", "Fail%"}:
            raise HudProtocolError(f"Measurement {command!r} failed: {response}")
        if not response.startswith(expected_prefix):
            raise HudProtocolError(
                f"Unexpected response to {command!r}; expected {expected_prefix!r}, got {response!r}"
            )
        return response


def run_tests(
    client: HudClient,
    configs: list[str],
    commands: list[str],
    switch_delay: float,
) -> list[TestResult]:
    results: list[TestResult] = []
    for config in configs:
        print(f"[{config}] switching configuration...", flush=True)
        client.switch_config(config)
        if switch_delay:
            time.sleep(switch_delay)

        for command in commands:
            print(f"[{config}] running {command}...", flush=True)
            response = client.measure(command)
            results.append(TestResult(config, command, response))
            print(f"[{config}] {response}", flush=True)
    return results


def run_cases(
    client: HudClient,
    cases: list[tuple[str, str]],
    switch_delay: float,
) -> list[TestResult]:
    """Run explicitly paired configuration/command cases."""
    results: list[TestResult] = []
    for config, command in cases:
        print(f"[{config}] switching configuration...", flush=True)
        client.switch_config(config)
        if switch_delay:
            time.sleep(switch_delay)
        print(f"[{config}] running {command}...", flush=True)
        response = client.measure(command)
        results.append(TestResult(config, command, response))
        print(f"[{config}] {response}", flush=True)
    return results


def load_test_plan(path: str) -> list[tuple[str, list[str]]]:
    """Read a literal TEST_PLAN assignment without executing the config file."""
    config_path = Path(path)
    try:
        tree = ast.parse(config_path.read_text(encoding="utf-8"), filename=str(config_path))
    except (OSError, SyntaxError) as exc:
        raise ValueError(f"Cannot read test plan {config_path}: {exc}") from exc

    raw_plan = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "TEST_PLAN" for target in node.targets
        ):
            try:
                raw_plan = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError) as exc:
                raise ValueError("TEST_PLAN must contain literal strings, lists, and tuples only") from exc
            break

    if raw_plan is None:
        raise ValueError(f"TEST_PLAN was not found in {config_path}")
    if not isinstance(raw_plan, (list, tuple)) or not raw_plan:
        raise ValueError("TEST_PLAN must be a non-empty list")

    plan: list[tuple[str, list[str]]] = []
    for index, item in enumerate(raw_plan, start=1):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError(f"TEST_PLAN item {index} must be (config, [commands])")
        config, commands = item
        if not isinstance(config, str) or not config.strip():
            raise ValueError(f"TEST_PLAN item {index} has an invalid config name")
        if not isinstance(commands, (list, tuple)) or not commands:
            raise ValueError(f"TEST_PLAN item {index} must contain at least one command")
        if not all(isinstance(command, str) and command.strip() for command in commands):
            raise ValueError(f"TEST_PLAN item {index} contains an invalid command")
        plan.append((config.strip(), [command.strip() for command in commands]))
    return plan


def run_test_plan(
    client: HudClient,
    plan: list[tuple[str, list[str]]],
    switch_delay: float,
) -> list[TestResult]:
    results: list[TestResult] = []
    for config, commands in plan:
        print(f"[{config}] switching configuration...", flush=True)
        client.switch_config(config)
        if switch_delay:
            time.sleep(switch_delay)
        for command in commands:
            print(f"[{config}] running {command}...", flush=True)
            response = client.measure(command)
            results.append(TestResult(config, command, response))
            print(f"[{config}] {response}", flush=True)
    return results


def parse_case(value: str) -> tuple[str, str]:
    try:
        config, command = value.rsplit(":", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Case must use CONFIG:COMMAND format, for example config1:t1"
        ) from exc
    if not config.strip() or not command.strip():
        raise argparse.ArgumentTypeError("Configuration and command cannot be empty")
    return config.strip(), command.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Switch HUD software configurations and run measurement commands."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--config",
        action="append",
        help="Configuration filename without extension; repeat for multiple configurations.",
    )
    parser.add_argument(
        "--test",
        action="append",
        help="Measurement command such as t1, t3, or t11/10/20; repeat as needed.",
    )
    parser.add_argument(
        "--case",
        action="append",
        type=parse_case,
        help="Paired CONFIG:COMMAND case; repeat as needed, e.g. --case config1:t1.",
    )
    parser.add_argument(
        "--plan",
        help="Python-style test plan file containing a literal TEST_PLAN list.",
    )
    parser.add_argument(
        "--switch-delay",
        type=float,
        default=0.2,
        help="Seconds to wait after switching configuration (default: 0.2).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.plan and not args.case and not (args.config and args.test):
        print(
            "ERROR: use --plan FILE, --case CONFIG:COMMAND, or both --config and --test",
            file=sys.stderr,
        )
        return 2
    try:
        with HudClient(args.host, args.port, args.timeout) as client:
            if args.plan:
                run_test_plan(client, load_test_plan(args.plan), args.switch_delay)
            elif args.case:
                run_cases(client, args.case, args.switch_delay)
            else:
                run_tests(client, args.config, args.test, args.switch_delay)
    except (OSError, HudProtocolError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
