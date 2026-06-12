#!/usr/bin/env python3
"""Black-box behavior tests for the llm-notify v3 decision table.

Drives the script only through its public surface: `event` / `watch`
subcommands with hook JSON on stdin, plus the documented test hooks
(LLM_NOTIFY_CONFIG, LLM_NOTIFY_STATE_DIR, LLM_NOTIFY_FAKE_IDLE,
LLM_NOTIFY_NO_SPAWN, LLM_NOTIFY_POLL). Feishu is mocked by a local
HTTP server so no real webhook is ever hit.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "llm-notify")


class FeishuMock(BaseHTTPRequestHandler):
    received = []
    # HTTP/1.1 keep-alive avoids a close-race with the client that
    # sporadically surfaces as ECONNRESET under HTTP/1.0.
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        FeishuMock.received.append(json.loads(self.rfile.read(length)))
        body = b'{"code": 0}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def texts():
    return [m["content"]["text"] for m in FeishuMock.received]


class LlmNotifyV3Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(SCRIPT, "r", encoding="utf-8") as f:
            src = f.read()
        if "LLM_NOTIFY_STATE_DIR" not in src or "LLM_NOTIFY_FAKE_IDLE" not in src:
            raise AssertionError(
                "llm-notify lacks the v3 test redirection hooks "
                "(LLM_NOTIFY_STATE_DIR / LLM_NOTIFY_FAKE_IDLE); refusing to run "
                "against a build that would touch real config/state."
            )
        cls.server = HTTPServer(("127.0.0.1", 0), FeishuMock)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.webhook = f"http://127.0.0.1:{cls.server.server_port}/hook"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        FeishuMock.received.clear()
        self.tmp = tempfile.mkdtemp(prefix="lnt-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.state = os.path.join(self.tmp, "state")
        self.config_path = os.path.join(self.tmp, "config.json")
        self.write_config()

    def write_config(self, **over):
        cfg = {
            "webhook": self.webhook,
            "keyword": "[AI通知]",
            "machine_label": "testbox",
            "presence": {"away_threshold": 120, "windows_input": False},
            "notify": {"min_elapsed": 0, "queue_ttl": 1800, "intervention_cooldown": 600},
            "content": {"max_changed_files": 10, "include_privacy_note": True},
        }
        for key, value in over.items():
            if isinstance(value, dict):
                cfg.setdefault(key, {}).update(value)
            else:
                cfg[key] = value
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f)

    def run_cmd(self, args, payload=None, idle=0):
        env = dict(
            os.environ,
            LLM_NOTIFY_CONFIG=self.config_path,
            LLM_NOTIFY_STATE_DIR=self.state,
            LLM_NOTIFY_NO_SPAWN="1",
            LLM_NOTIFY_FAKE_IDLE=str(idle),
            LLM_NOTIFY_POLL="1",
        )
        return subprocess.run(
            [sys.executable, SCRIPT, *args],
            input=json.dumps(payload if payload is not None else {}),
            text=True,
            capture_output=True,
            env=env,
            timeout=30,
        )

    def event(self, payload, idle=0, tool="claude"):
        result = self.run_cmd(["event", tool], payload, idle)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        return result

    def watch(self, idle=999):
        result = self.run_cmd(["watch"], None, idle)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        return result

    def queue(self):
        qdir = os.path.join(self.state, "queue")
        if not os.path.isdir(qdir):
            return []
        entries = []
        for name in sorted(os.listdir(qdir)):
            if name.endswith(".json"):
                with open(os.path.join(qdir, name), encoding="utf-8") as f:
                    entries.append(json.load(f))
        return entries

    def prompt(self, sid="s1", text="do something", idle=0):
        self.event(
            {"hook_event_name": "UserPromptSubmit", "session_id": sid, "prompt": text, "cwd": self.tmp},
            idle=idle,
        )

    def stop(self, sid="s1", idle=0):
        self.event({"hook_event_name": "Stop", "session_id": sid, "cwd": self.tmp}, idle=idle)

    # --- Stop decisions ---

    def test_short_turn_is_silent_even_when_away(self):
        self.write_config(notify={"min_elapsed": 3600})
        self.prompt()
        self.stop(idle=999)
        self.assertEqual(FeishuMock.received, [])
        self.assertEqual(self.queue(), [])

    def test_present_completion_is_queued_not_sent(self):
        self.prompt()
        self.stop(idle=0)
        self.assertEqual(FeishuMock.received, [])
        entries = self.queue()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["kind"], "completion")

    def test_away_completion_sends_immediately(self):
        self.prompt()
        self.stop(idle=999)
        self.assertEqual(len(FeishuMock.received), 1)
        self.assertIn("任务完成", texts()[0])
        self.assertIn("离开时完成", texts()[0])
        self.assertIn("[AI通知]", texts()[0])
        self.assertEqual(self.queue(), [])

    def test_explicit_request_sends_even_when_present(self):
        self.prompt(text="跑完测试后通知我")
        self.stop(idle=0)
        self.assertEqual(len(FeishuMock.received), 1)
        self.assertIn("显式要求通知", texts()[0])

    def test_new_prompt_cancels_queued_completion(self):
        self.prompt()
        self.stop(idle=0)
        self.assertEqual(len(self.queue()), 1)
        self.prompt(text="next request")
        self.assertEqual(self.queue(), [])
        self.assertEqual(FeishuMock.received, [])

    def test_tool_failures_do_not_shortcircuit_and_appear_in_body(self):
        self.prompt()
        for _ in range(2):
            self.event(
                {"hook_event_name": "PostToolUseFailure", "session_id": "s1", "tool_name": "Bash"},
                idle=0,
            )
        self.stop(idle=0)
        # present + failures: still queued, NOT sent (v2 would have fired "任务存在失败")
        self.assertEqual(FeishuMock.received, [])
        self.assertEqual(len(self.queue()), 1)
        self.watch(idle=999)
        self.assertEqual(len(FeishuMock.received), 1)
        self.assertIn("失败 2 次", texts()[0])

    # --- Watcher ---

    def test_watcher_aggregates_multiple_sessions_into_one_message(self):
        for sid in ("s1", "s2"):
            self.prompt(sid=sid)
            self.stop(sid=sid, idle=0)
        self.assertEqual(len(self.queue()), 2)
        self.watch(idle=999)
        self.assertEqual(len(FeishuMock.received), 1)
        self.assertIn("2 项更新", texts()[0])
        self.assertEqual(self.queue(), [])

    def test_expired_entries_are_dropped_not_sent(self):
        self.write_config(notify={"queue_ttl": 0})
        self.prompt()
        self.stop(idle=0)
        self.assertEqual(len(self.queue()), 1)
        self.watch(idle=999)
        self.assertEqual(FeishuMock.received, [])
        self.assertEqual(self.queue(), [])

    # --- Interventions ---

    def test_permission_prompt_present_queues_then_tool_activity_clears(self):
        self.prompt()
        self.event(
            {
                "hook_event_name": "Notification",
                "session_id": "s1",
                "notification_type": "permission_prompt",
                "cwd": self.tmp,
            },
            idle=0,
        )
        self.assertEqual(FeishuMock.received, [])
        entries = self.queue()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["kind"], "intervention")
        self.event(
            {"hook_event_name": "PostToolUse", "session_id": "s1", "tool_name": "Bash"},
            idle=0,
        )
        self.assertEqual(self.queue(), [])

    def test_permission_prompt_away_sends_with_cooldown(self):
        self.prompt()
        payload = {
            "hook_event_name": "Notification",
            "session_id": "s1",
            "notification_type": "permission_prompt",
            "cwd": self.tmp,
        }
        self.event(payload, idle=999)
        self.assertEqual(len(FeishuMock.received), 1)
        self.assertIn("需要处理", texts()[0])
        self.event(payload, idle=999)
        self.assertEqual(len(FeishuMock.received), 1, "cooldown should suppress the second send")

    def test_idle_prompt_notifications_are_ignored(self):
        self.prompt()
        self.event(
            {"hook_event_name": "Notification", "session_id": "s1", "notification_type": "idle_prompt"},
            idle=999,
        )
        self.assertEqual(FeishuMock.received, [])
        self.assertEqual(self.queue(), [])

    def test_stopfailure_away_sends_classified_error(self):
        self.prompt()
        self.event(
            {"hook_event_name": "StopFailure", "session_id": "s1", "error": "rate limit exceeded"},
            idle=999,
        )
        self.assertEqual(len(FeishuMock.received), 1)
        self.assertIn("需要处理", texts()[0])
        self.assertIn("rate_limit", texts()[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
