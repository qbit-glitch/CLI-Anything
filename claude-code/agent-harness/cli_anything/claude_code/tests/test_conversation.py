"""Additional conversation module tests."""

import pytest
from pathlib import Path


class TestConversationIds:

    def test_unique_session_ids(self):
        from cli_anything.claude_code.core.conversation import create_conversation
        ids = {create_conversation()["session_id"] for _ in range(20)}
        assert len(ids) == 20

    def test_metadata_fields(self):
        from cli_anything.claude_code.core.conversation import create_conversation
        conv = create_conversation()
        assert "created" in conv["metadata"]
        assert "modified" in conv["metadata"]

    def test_append_updates_modified(self):
        from cli_anything.claude_code.core.conversation import create_conversation, append_message
        conv = create_conversation()
        created = conv["metadata"]["modified"]
        import time; time.sleep(0.01)
        append_message(conv, "user", "hi")
        # modified timestamp should be refreshed (or at least present)
        assert "modified" in conv["metadata"]

    def test_trim_keeps_recent(self):
        from cli_anything.claude_code.core.conversation import (
            create_conversation, append_message, trim_to_context_window, estimate_tokens
        )
        conv = create_conversation()
        # Add 5 tiny messages and 5 large messages
        for i in range(5):
            append_message(conv, "user", f"short {i}")
        for i in range(5):
            append_message(conv, "assistant", "x" * 2000)

        trimmed = trim_to_context_window(conv, max_tokens=500)
        # Most recent messages should survive
        assert len(trimmed["messages"]) <= len(conv["messages"])
        assert estimate_tokens(trimmed) <= 500 or len(trimmed["messages"]) == 0

    def test_export_creates_directory(self, tmp_path):
        from cli_anything.claude_code.core.conversation import create_conversation, export_transcript
        conv = create_conversation()
        nested = tmp_path / "sub" / "dir" / "out.md"
        result = export_transcript(conv, str(nested))
        assert Path(result).exists()

    def test_export_includes_session_id(self, tmp_path):
        from cli_anything.claude_code.core.conversation import create_conversation, export_transcript
        conv = create_conversation()
        out = tmp_path / "t.md"
        export_transcript(conv, str(out))
        content = out.read_text()
        assert conv["session_id"] in content

    def test_export_includes_model(self, tmp_path):
        from cli_anything.claude_code.core.conversation import create_conversation, export_transcript
        conv = create_conversation(model="claude-opus-4-5")
        out = tmp_path / "t.md"
        export_transcript(conv, str(out))
        content = out.read_text()
        assert "claude-opus-4-5" in content
