import socket
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hud_client import (
    HudClient,
    HudProtocolError,
    load_test_plan,
    parse_case,
    run_cases,
    run_test_plan,
    run_tests,
)


class FakeHudServer:
    def __init__(self, replies: list[tuple[str, str]]):
        self.replies = replies
        self.received: list[str] = []
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind(("127.0.0.1", 0))
        self.socket.listen(1)
        self.host, self.port = self.socket.getsockname()
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.socket.close()
        self.thread.join(timeout=1)

    def _serve(self):
        connection, _ = self.socket.accept()
        with connection:
            for expected_command, reply in self.replies:
                data = bytearray()
                while expected_command.encode() not in data:
                    chunk = connection.recv(4096)
                    if not chunk:
                        return
                    data.extend(chunk)
                self.received.append(data.decode())
                connection.sendall(reply.encode())


class HudClientTests(unittest.TestCase):
    def test_switches_configs_and_runs_measurements(self):
        replies = [
            ("gin%", "OK%"),
            ("c-day%", "OK%"),
            ("t1%", "t1_Result:1 2 3,%"),
            ("c-night%", "OK%"),
            ("t1%", "t1_Result:4 5 6,%"),
        ]
        with FakeHudServer(replies) as server:
            with HudClient(server.host, server.port, timeout=1) as client:
                self.assertTrue(client.camera_ready())
                results = run_tests(client, ["day", "night"], ["t1"], 0)

        self.assertEqual([result.config for result in results], ["day", "night"])
        self.assertTrue(all(result.response.startswith("t1_Result:") for result in results))

    def test_rejects_failed_config_switch(self):
        with FakeHudServer([("c-missing%", "Fail%")]) as server:
            with HudClient(server.host, server.port, timeout=1) as client:
                with self.assertRaises(HudProtocolError):
                    client.switch_config("missing.ini")

    def test_runs_paired_cases(self):
        replies = [
            ("c-config1%", "OK%"),
            ("t1%", "t1_Result:1,%"),
            ("c-config2%", "OK%"),
            ("t3%", "t3_Result:3,%"),
        ]
        with FakeHudServer(replies) as server:
            with HudClient(server.host, server.port, timeout=1) as client:
                results = run_cases(client, [("config1", "t1"), ("config2", "t3")], 0)
        self.assertEqual(
            [(result.config, result.command) for result in results],
            [("config1", "t1"), ("config2", "t3")],
        )

    def test_parses_case_from_right(self):
        self.assertEqual(parse_case("config1:t11/10/20"), ("config1", "t11/10/20"))

    def test_loads_separate_plan_with_multiple_commands(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "plan.py"
            path.write_text('TEST_PLAN = [("11", ["t24", "t1"]), ("22", ["t3"])]\n')
            self.assertEqual(
                load_test_plan(str(path)),
                [("11", ["t24", "t1"]), ("22", ["t3"])],
            )

    def test_runs_all_commands_for_each_plan_config(self):
        replies = [
            ("c-11%", "OK%"),
            ("t24%", "t24_Result:1,%"),
            ("t1%", "t1_Result:2,%"),
            ("c-22%", "OK%"),
            ("t3%", "t3_Result:3,%"),
        ]
        with FakeHudServer(replies) as server:
            with HudClient(server.host, server.port, timeout=1) as client:
                results = run_test_plan(
                    client, [("11", ["t24", "t1"]), ("22", ["t3"])], 0
                )
        self.assertEqual(
            [(result.config, result.command) for result in results],
            [("11", "t24"), ("11", "t1"), ("22", "t3")],
        )


if __name__ == "__main__":
    unittest.main()
