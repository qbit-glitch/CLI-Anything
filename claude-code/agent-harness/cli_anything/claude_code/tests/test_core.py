"""Unit tests for Claude Code CLI harness core modules.

No backend software required — all tests run against pure Python logic.
"""

import json
import copy
import pytest
import tempfile
import os
from pathlib import Path


# ── TestConversation ──────────────────────────────────────────────

class TestConversation:

    def setup_method(self):
        from cli_anything.claude_code.core.conversation import create_conversation
        self.conv = create_conversation(model="claude-sonnet-4-6", system_prompt="Be helpful.")

    def test_create(self):
        from cli_anything.claude_code.core.conversation import create_conversation
        conv = create_conversation()
        assert "session_id" in conv
        assert conv["model"] == "claude-sonnet-4-6"
        assert conv["messages"] == []
        assert conv["system_prompt"] is None
        assert "created" in conv["metadata"]

    def test_create_with_system_prompt(self):
        from cli_anything.claude_code.core.conversation import create_conversation
        conv = create_conversation(system_prompt="You are a helpful assistant.")
        assert conv["system_prompt"] == "You are a helpful assistant."

    def test_append_message(self):
        from cli_anything.claude_code.core.conversation import append_message
        append_message(self.conv, "user", "Hello!")
        assert len(self.conv["messages"]) == 1
        assert self.conv["messages"][0]["role"] == "user"
        assert self.conv["messages"][0]["content"] == "Hello!"

    def test_append_message_multiple(self):
        from cli_anything.claude_code.core.conversation import append_message
        append_message(self.conv, "user", "Hello!")
        append_message(self.conv, "assistant", "Hi there!")
        assert len(self.conv["messages"]) == 2
        assert self.conv["messages"][1]["role"] == "assistant"

    def test_append_message_with_tool_calls(self):
        from cli_anything.claude_code.core.conversation import append_message
        tool_calls = [{"name": "Bash", "args": {"command": "ls"}}]
        append_message(self.conv, "assistant", "Running bash...", tool_calls=tool_calls)
        assert self.conv["messages"][0].get("tool_calls") == tool_calls
        assert len(self.conv["tool_calls"]) == 1

    def test_estimate_tokens(self):
        from cli_anything.claude_code.core.conversation import append_message, estimate_tokens
        # system prompt "Be helpful." = 11 chars → 2 tokens
        append_message(self.conv, "user", "Hello world")  # 11 chars → 2 tokens
        tokens = estimate_tokens(self.conv)
        assert tokens > 0
        assert isinstance(tokens, int)

    def test_estimate_tokens_empty(self):
        from cli_anything.claude_code.core.conversation import create_conversation, estimate_tokens
        conv = create_conversation()
        assert estimate_tokens(conv) == 0

    def test_trim_to_context_window(self):
        from cli_anything.claude_code.core.conversation import append_message, trim_to_context_window
        # Add messages with a lot of content
        for i in range(10):
            append_message(self.conv, "user", "x" * 1000)
            append_message(self.conv, "assistant", "y" * 1000)
        original_count = len(self.conv["messages"])
        trimmed = trim_to_context_window(self.conv, max_tokens=100)
        assert len(trimmed["messages"]) < original_count

    def test_trim_to_context_window_does_not_mutate(self):
        from cli_anything.claude_code.core.conversation import append_message, trim_to_context_window
        for i in range(5):
            append_message(self.conv, "user", "x" * 500)
        original_count = len(self.conv["messages"])
        trimmed = trim_to_context_window(self.conv, max_tokens=10)
        # Original should be unchanged
        assert len(self.conv["messages"]) == original_count

    def test_export_transcript(self, tmp_path):
        from cli_anything.claude_code.core.conversation import append_message, export_transcript
        append_message(self.conv, "user", "Hello!")
        append_message(self.conv, "assistant", "Hi there!")
        out = tmp_path / "transcript.md"
        result = export_transcript(self.conv, str(out))
        assert result == str(out)
        content = out.read_text(encoding="utf-8")
        assert "Conversation Transcript" in content
        assert "Hello!" in content
        assert "Hi there!" in content
        assert "USER" in content
        assert "ASSISTANT" in content


# ── TestSession ──────────────────────────────────────────────

class TestSession:

    def setup_method(self):
        from cli_anything.claude_code.core.session import Session
        self.session = Session()

    def test_initial_state(self):
        sess = self.session
        assert sess.has_project()
        assert sess._undo_stack == []
        assert sess._redo_stack == []
        assert not sess._modified

    def test_snapshot(self):
        sess = self.session
        sess.snapshot("first change")
        assert len(sess._undo_stack) == 1
        assert sess._undo_stack[0]["description"] == "first change"
        assert sess._modified

    def test_undo_redo(self):
        from cli_anything.claude_code.core.conversation import append_message
        sess = self.session
        original_count = len(sess.project["messages"])
        sess.snapshot("before append")
        append_message(sess.project, "user", "Test message")
        assert len(sess.project["messages"]) == original_count + 1

        desc = sess.undo()
        assert desc == "before append"
        assert len(sess.project["messages"]) == original_count

        sess.redo()
        assert len(sess.project["messages"]) == original_count + 1

    def test_undo_empty_raises(self):
        sess = self.session
        with pytest.raises(RuntimeError, match="Nothing to undo"):
            sess.undo()

    def test_redo_empty_raises(self):
        sess = self.session
        with pytest.raises(RuntimeError, match="Nothing to redo"):
            sess.redo()

    def test_max_undo_limit(self):
        from cli_anything.claude_code.core.session import Session
        sess = Session()
        for i in range(Session.MAX_UNDO + 10):
            sess.snapshot(f"change {i}")
        assert len(sess._undo_stack) == Session.MAX_UNDO

    def test_snapshot_clears_redo(self):
        sess = self.session
        sess.snapshot("s1")
        sess.undo()
        assert len(sess._redo_stack) == 1
        sess.snapshot("s2")
        assert len(sess._redo_stack) == 0

    def test_status(self):
        sess = self.session
        s = sess.status()
        assert "has_project" in s
        assert s["has_project"] is True
        assert "undo_count" in s
        assert "redo_count" in s
        assert "session_id" in s
        assert "model" in s
        assert "message_count" in s

    def test_save_and_load_session(self, tmp_path):
        from cli_anything.claude_code.core.session import Session
        sess = Session()
        path = str(tmp_path / "session.json")
        saved = sess.save_session(path)
        assert saved == path
        assert not sess._modified

        sess2 = Session()
        sess2.load_session(path)
        assert sess2.project["session_id"] == sess.project["session_id"]
        assert sess2.project["model"] == sess.project["model"]

    def test_save_without_path_raises(self):
        from cli_anything.claude_code.core.session import Session
        sess = Session()
        sess.project_path = None
        with pytest.raises(ValueError):
            sess.save_session()


# ── TestAgents ──────────────────────────────────────────────

class TestAgents:

    def test_create_agent(self):
        from cli_anything.claude_code.core.agents import create_agent
        agent = create_agent(
            name="test-agent",
            system_prompt="You are a test agent.",
            model="claude-sonnet-4-6",
        )
        assert agent["name"] == "test-agent"
        assert agent["system_prompt"] == "You are a test agent."
        assert agent["model"] == "claude-sonnet-4-6"
        assert agent["allowed_tools"] == []
        assert agent["disallowed_tools"] == []
        assert agent["permission_mode"] == "default"

    def test_create_agent_with_tools(self):
        from cli_anything.claude_code.core.agents import create_agent
        agent = create_agent(
            name="coder",
            system_prompt="Write code.",
            allowed_tools=["Bash", "Read", "Write"],
            disallowed_tools=["WebSearch"],
        )
        assert "Bash" in agent["allowed_tools"]
        assert "WebSearch" in agent["disallowed_tools"]

    def test_save_load_agent(self, tmp_path):
        from cli_anything.claude_code.core.agents import create_agent, save_agent, list_agents
        agent = create_agent("my-agent", "Test system prompt.")
        path = save_agent(agent, config_dir=str(tmp_path))
        assert Path(path).exists()

        agents = list_agents(config_dir=str(tmp_path))
        assert len(agents) == 1
        assert agents[0]["name"] == "my-agent"

    def test_save_multiple_agents(self, tmp_path):
        from cli_anything.claude_code.core.agents import create_agent, save_agent, list_agents
        for name in ["alpha", "beta", "gamma"]:
            agent = create_agent(name, f"Prompt for {name}.")
            save_agent(agent, config_dir=str(tmp_path))
        agents = list_agents(config_dir=str(tmp_path))
        assert len(agents) == 3

    def test_delete_agent(self, tmp_path):
        from cli_anything.claude_code.core.agents import create_agent, save_agent, delete_agent, list_agents
        agent = create_agent("del-agent", "To be deleted.")
        save_agent(agent, config_dir=str(tmp_path))
        delete_agent("del-agent", config_dir=str(tmp_path))
        agents = list_agents(config_dir=str(tmp_path))
        assert all(a["name"] != "del-agent" for a in agents)

    def test_delete_nonexistent_agent_raises(self, tmp_path):
        from cli_anything.claude_code.core.agents import delete_agent
        with pytest.raises(FileNotFoundError):
            delete_agent("ghost-agent", config_dir=str(tmp_path))


# ── TestMcpConfig ──────────────────────────────────────────────

class TestMcpConfig:

    def _make_settings(self, tmp_path, content: dict) -> str:
        p = tmp_path / "settings.json"
        p.write_text(json.dumps(content), encoding="utf-8")
        return str(p)

    def test_list_servers_empty(self, tmp_path):
        from cli_anything.claude_code.core.mcp_config import list_mcp_servers
        path = self._make_settings(tmp_path, {})
        servers = list_mcp_servers(settings_path=path)
        assert servers == []

    def test_list_servers(self, tmp_path):
        from cli_anything.claude_code.core.mcp_config import list_mcp_servers
        content = {
            "mcpServers": {
                "myserver": {"command": "npx", "args": ["-y", "@myorg/mcp"]},
            }
        }
        path = self._make_settings(tmp_path, content)
        servers = list_mcp_servers(settings_path=path)
        assert len(servers) == 1
        assert servers[0]["name"] == "myserver"
        assert servers[0]["command"] == "npx"

    def test_add_server(self, tmp_path):
        from cli_anything.claude_code.core.mcp_config import add_mcp_server, list_mcp_servers
        path = self._make_settings(tmp_path, {})
        add_mcp_server("fs", "npx", args=["-y", "@mcp/fs"], settings_path=path)
        servers = list_mcp_servers(settings_path=path)
        assert len(servers) == 1
        assert servers[0]["name"] == "fs"
        assert servers[0]["command"] == "npx"
        assert servers[0]["args"] == ["-y", "@mcp/fs"]

    def test_add_server_with_env(self, tmp_path):
        from cli_anything.claude_code.core.mcp_config import add_mcp_server, list_mcp_servers
        path = self._make_settings(tmp_path, {})
        add_mcp_server("envserver", "python", env={"MY_KEY": "abc"}, settings_path=path)
        servers = list_mcp_servers(settings_path=path)
        assert servers[0]["env"] == {"MY_KEY": "abc"}

    def test_add_server_idempotent(self, tmp_path):
        from cli_anything.claude_code.core.mcp_config import add_mcp_server, list_mcp_servers
        path = self._make_settings(tmp_path, {})
        add_mcp_server("svc", "npx", settings_path=path)
        add_mcp_server("svc", "python", settings_path=path)  # overwrite
        servers = list_mcp_servers(settings_path=path)
        assert len(servers) == 1
        assert servers[0]["command"] == "python"

    def test_remove_server(self, tmp_path):
        from cli_anything.claude_code.core.mcp_config import add_mcp_server, remove_mcp_server, list_mcp_servers
        path = self._make_settings(tmp_path, {})
        add_mcp_server("todel", "npx", settings_path=path)
        remove_mcp_server("todel", settings_path=path)
        servers = list_mcp_servers(settings_path=path)
        assert servers == []

    def test_remove_nonexistent_raises(self, tmp_path):
        from cli_anything.claude_code.core.mcp_config import remove_mcp_server
        path = self._make_settings(tmp_path, {})
        with pytest.raises(KeyError):
            remove_mcp_server("ghost", settings_path=path)

    def test_list_missing_file(self, tmp_path):
        from cli_anything.claude_code.core.mcp_config import list_mcp_servers
        path = str(tmp_path / "nonexistent.json")
        servers = list_mcp_servers(settings_path=path)
        assert servers == []
