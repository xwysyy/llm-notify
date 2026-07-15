#!/usr/bin/env python3
"""Black-box behavior tests for the llm-notify v4 decision table.

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

SCRIPT = os.environ.get("LLM_NOTIFY_SCRIPT") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "llm-notify"
)


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


class LlmNotifyV4Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(SCRIPT, "r", encoding="utf-8") as f:
            src = f.read()
        if "LLM_NOTIFY_STATE_DIR" not in src or "LLM_NOTIFY_FAKE_IDLE" not in src:
            raise AssertionError(
                "llm-notify lacks the test redirection hooks "
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
        self.project = os.path.basename(self.tmp)
        self.write_config()

    def write_config(self, **over):
        cfg = {
            "webhook": self.webhook,
            "keyword": "[AI通知]",
            "presence": {"away_threshold": 120, "windows_input": False},
            "notify": {
                "min_elapsed": 0,
                "queue_ttl": 1800,
                "intervention_cooldown": 600,
                "debounce": 0,
                "seen_grace": 180,
                # off by default in tests: pending reminders keep the watcher
                # alive, which would hang tests that drain the queue
                "reply_reminders": [],
            },
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

    def run_init(self, reminders=""):
        env = dict(
            os.environ,
            LLM_NOTIFY_CONFIG=self.config_path,
            LLM_NOTIFY_STATE_DIR=self.state,
            LLM_NOTIFY_NO_SPAWN="1",
            LLM_NOTIFY_FAKE_IDLE="0",
        )
        answers = [self.webhook, "", "", "120", reminders]
        return subprocess.run(
            [sys.executable, SCRIPT, "init"],
            input="\n".join(answers) + "\n",
            text=True,
            capture_output=True,
            env=env,
            timeout=30,
        )

    def read_config(self):
        with open(self.config_path, encoding="utf-8") as f:
            return json.load(f)

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

    def prompt(self, sid="s1", text="do something", idle=0, cwd=None):
        self.event(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": sid,
                "prompt": text,
                "cwd": cwd or self.tmp,
            },
            idle=idle,
        )

    def stop(self, sid="s1", idle=0):
        self.event({"hook_event_name": "Stop", "session_id": sid, "cwd": self.tmp}, idle=idle)

    # --- Init configuration ---

    def test_init_defaults_to_four_reply_reminders(self):
        result = self.run_init()
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(
            self.read_config()["notify"]["reply_reminders"],
            [1500, 2100, 2700, 3300],
        )

    def test_init_accepts_custom_reply_reminder_minutes(self):
        result = self.run_init("10,20,30")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(
            self.read_config()["notify"]["reply_reminders"],
            [600, 1200, 1800],
        )

    def test_init_can_disable_reply_reminders(self):
        result = self.run_init("none")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(self.read_config()["notify"]["reply_reminders"], [])

    def test_init_rejects_invalid_reply_reminder_minutes(self):
        result = self.run_init("35,25")
        self.assertEqual(result.returncode, 1)
        self.assertIn("未回复提醒必须是", result.stderr)

    # --- Stop decisions ---

    def test_short_turn_is_silent_even_when_away(self):
        self.write_config(notify={"min_elapsed": 3600})
        self.prompt()
        self.stop(idle=999)
        self.assertEqual(FeishuMock.received, [])
        self.assertEqual(self.queue(), [])

    def test_stop_always_queues_watcher_is_sole_sender(self):
        self.prompt()
        self.stop(idle=999)
        self.assertEqual(FeishuMock.received, [])
        entries = self.queue()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["kind"], "completion")
        self.watch(idle=999)
        self.assertEqual(texts(), [f"[AI通知] {self.project} 完成"])
        self.assertEqual(self.queue(), [])

    def test_message_is_single_line_without_agent_or_paths(self):
        self.prompt()
        self.stop(idle=999)
        self.watch(idle=999)
        text = texts()[0]
        self.assertNotIn("\n", text)
        self.assertNotIn("Claude", text)
        self.assertNotIn(self.tmp, text)  # basename only, never the absolute path

    def test_explicit_request_sends_even_when_present(self):
        self.prompt(text="跑完测试后通知我")
        self.stop(idle=0)
        self.assertEqual(texts(), [f"[AI通知] {self.project} 完成"])

    def test_new_prompt_cancels_queued_completion(self):
        self.prompt()
        self.stop(idle=0)
        self.assertEqual(len(self.queue()), 1)
        self.prompt(text="next request")
        self.assertEqual(self.queue(), [])
        self.assertEqual(FeishuMock.received, [])

    # --- Watcher ---

    def test_watcher_aggregates_multiple_projects_into_one_line(self):
        proj_a = os.path.join(self.tmp, "proj-a")
        proj_b = os.path.join(self.tmp, "proj-b")
        os.makedirs(proj_a)
        os.makedirs(proj_b)
        for sid, cwd in (("s1", proj_a), ("s2", proj_b)):
            self.prompt(sid=sid, cwd=cwd)
            self.event({"hook_event_name": "Stop", "session_id": sid, "cwd": cwd}, idle=0)
        self.assertEqual(len(self.queue()), 2)
        self.watch(idle=999)
        self.assertEqual(len(FeishuMock.received), 1)
        text = texts()[0]
        self.assertNotIn("\n", text)
        self.assertIn("proj-a 完成", text)
        self.assertIn("proj-b 完成", text)
        self.assertIn(" · ", text)
        self.assertEqual(self.queue(), [])

    def test_same_project_same_state_collapses_to_one_part(self):
        for sid in ("s1", "s2"):
            self.prompt(sid=sid)
            self.stop(sid=sid, idle=0)
        self.watch(idle=999)
        self.assertEqual(len(FeishuMock.received), 1)
        self.assertEqual(texts()[0].count("完成"), 1)

    def test_expired_entries_are_dropped_not_sent(self):
        self.write_config(notify={"queue_ttl": 0})
        self.prompt()
        self.stop(idle=0)
        self.assertEqual(len(self.queue()), 1)
        self.watch(idle=999)
        self.assertEqual(FeishuMock.received, [])
        self.assertEqual(self.queue(), [])

    def test_completion_watched_past_seen_grace_is_dropped(self):
        self.write_config(notify={"seen_grace": 0})
        self.prompt()
        self.stop(idle=0)
        self.assertEqual(len(self.queue()), 1)
        # user is present at the poll and the grace window has passed: seen
        self.watch(idle=0)
        self.assertEqual(FeishuMock.received, [])
        self.assertEqual(self.queue(), [])

    def test_sent_turn_is_never_resent(self):
        self.prompt()
        self.stop(idle=999)
        entry = self.queue()[0]
        self.watch(idle=999)
        self.assertEqual(len(FeishuMock.received), 1)
        # resurrect the already-sent entry (simulates a lost-update race)
        qdir = os.path.join(self.state, "queue")
        with open(os.path.join(qdir, entry["id"] + ".json"), "w", encoding="utf-8") as f:
            json.dump(entry, f)
        self.watch(idle=999)
        self.assertEqual(len(FeishuMock.received), 1, "same turn must not be sent twice")
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
        self.assertEqual(entries[0]["state"], "需确认")
        self.event(
            {"hook_event_name": "PostToolUse", "session_id": "s1", "tool_name": "Bash"},
            idle=0,
        )
        self.assertEqual(self.queue(), [])

    def test_permission_prompt_away_sends_once_with_cooldown(self):
        self.prompt()
        payload = {
            "hook_event_name": "Notification",
            "session_id": "s1",
            "notification_type": "permission_prompt",
            "cwd": self.tmp,
        }
        self.event(payload, idle=999)
        self.assertEqual(FeishuMock.received, [])
        self.watch(idle=999)
        self.assertEqual(texts(), [f"[AI通知] {self.project} 需确认"])
        self.event(payload, idle=999)
        self.watch(idle=999)
        self.assertEqual(len(FeishuMock.received), 1, "cooldown should suppress the second send")

    def test_idle_prompt_notifications_are_ignored(self):
        self.prompt()
        self.event(
            {"hook_event_name": "Notification", "session_id": "s1", "notification_type": "idle_prompt"},
            idle=999,
        )
        self.assertEqual(FeishuMock.received, [])
        self.assertEqual(self.queue(), [])

    # --- Reply reminders ---

    def session_files(self):
        sdir = os.path.join(self.state, "sessions")
        return [os.path.join(sdir, n) for n in os.listdir(sdir)]

    def patch_sessions(self, **fields):
        for path in self.session_files():
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data.update(fields)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)

    def test_stop_schedules_reply_reminders(self):
        self.write_config(notify={"reply_reminders": [2400, 3000]})
        self.prompt()
        self.stop(idle=0)
        reminders = [e for e in self.queue() if e["kind"] == "reminder"]
        self.assertEqual(len(reminders), 2)
        self.assertEqual(
            {r["state"] for r in reminders}, {"40分钟未回复", "50分钟未回复"}
        )
        offsets = sorted(r["fire_at"] - r["created_at"] for r in reminders)
        self.assertEqual(offsets, [2400.0, 3000.0])

    def test_intervention_schedules_reply_reminders(self):
        self.write_config(notify={"reply_reminders": [2400]})
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
        kinds = sorted(e["kind"] for e in self.queue())
        self.assertEqual(kinds, ["intervention", "reminder"])

    def test_new_prompt_cancels_reminders(self):
        self.write_config(notify={"reply_reminders": [2400]})
        self.prompt()
        self.stop(idle=0)
        self.assertTrue(any(e["kind"] == "reminder" for e in self.queue()))
        self.prompt(text="reply arrived")
        self.assertEqual([e for e in self.queue() if e["kind"] == "reminder"], [])

    def test_tool_activity_cancels_reminders_via_sweep(self):
        self.write_config(notify={"reply_reminders": [2400]})
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
        self.event(
            {"hook_event_name": "PostToolUse", "session_id": "s1", "tool_name": "Bash"},
            idle=0,
        )
        self.watch(idle=0)
        self.assertEqual(FeishuMock.received, [])
        self.assertEqual(self.queue(), [])

    def test_due_reminder_sends_even_when_present(self):
        self.write_config(notify={"reply_reminders": [0], "min_elapsed": 3600})
        self.prompt()
        self.stop(idle=0)
        self.assertEqual([e["kind"] for e in self.queue()], ["reminder"])
        # idle=0: user is at the keyboard, yet the reminder must go out
        self.watch(idle=0)
        self.assertEqual(texts(), [f"[AI通知] {self.project} 0分钟未回复"])
        self.assertEqual(self.queue(), [])

    def test_session_end_cancels_all_pending_entries(self):
        self.write_config(notify={"reply_reminders": [2400]})
        self.prompt()
        self.stop(idle=0)
        self.assertNotEqual(self.queue(), [])
        self.event(
            {
                "hook_event_name": "SessionEnd",
                "session_id": "s1",
                "reason": "prompt_input_exit",
                "cwd": self.tmp,
            }
        )
        self.assertEqual(self.queue(), [])
        self.assertEqual(FeishuMock.received, [])

    def test_dead_claude_process_cancels_reminder(self):
        self.write_config(notify={"reply_reminders": [0], "min_elapsed": 3600})
        self.prompt()
        self.stop(idle=0)
        # live pid but wrong start time: the recorded process is gone (pid reused)
        self.patch_sessions(agent_pid=os.getpid(), agent_pid_start="0")
        self.watch(idle=0)
        self.assertEqual(FeishuMock.received, [])
        self.assertEqual(self.queue(), [])

    def test_live_claude_process_keeps_reminder(self):
        self.write_config(notify={"reply_reminders": [0], "min_elapsed": 3600})
        self.prompt()
        self.stop(idle=0)
        with open(f"/proc/{os.getpid()}/stat", encoding="utf-8") as f:
            start = f.read().rpartition(")")[2].split()[19]
        self.patch_sessions(agent_pid=os.getpid(), agent_pid_start=start)
        self.watch(idle=0)
        self.assertEqual(texts(), [f"[AI通知] {self.project} 0分钟未回复"])

    def test_sent_reminder_is_never_resent(self):
        self.write_config(notify={"reply_reminders": [0], "min_elapsed": 3600})
        self.prompt()
        self.stop(idle=0)
        entry = self.queue()[0]
        self.watch(idle=0)
        self.assertEqual(len(FeishuMock.received), 1)
        qdir = os.path.join(self.state, "queue")
        with open(os.path.join(qdir, entry["id"] + ".json"), "w", encoding="utf-8") as f:
            json.dump(entry, f)
        self.watch(idle=0)
        self.assertEqual(len(FeishuMock.received), 1, "same reminder must not be sent twice")
        self.assertEqual(self.queue(), [])

    def test_codex_sessions_get_no_reminders(self):
        self.write_config(notify={"reply_reminders": [2400]})
        self.event(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "c1",
                "prompt": "do something",
                "cwd": self.tmp,
            },
            tool="codex",
        )
        self.event(
            {"hook_event_name": "Stop", "session_id": "c1", "cwd": self.tmp},
            tool="codex",
        )
        self.assertEqual([e["kind"] for e in self.queue()], ["completion"])

    def test_stopfailure_reports_error_state(self):
        self.prompt()
        self.event(
            {"hook_event_name": "StopFailure", "session_id": "s1", "error": "rate limit exceeded"},
            idle=999,
        )
        self.assertEqual(FeishuMock.received, [])
        self.watch(idle=999)
        self.assertEqual(texts(), [f"[AI通知] {self.project} 出错"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
