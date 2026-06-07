from __future__ import annotations

import sys
from unittest.mock import MagicMock

# Inject mock modules into sys.modules before any code imports them.
# This lives at the project-root conftest so pytest picks it up for ALL
# test files — including backend/chatbot/tests/test_chatbot.py — because
# pytest walks conftest.py files from rootdir upward, making the root
# conftest visible to every subdirectory.
mock_transformers = MagicMock()
mock_pipeline = MagicMock()
mock_transformers.pipeline = mock_pipeline
sys.modules['transformers'] = mock_transformers

mock_torch = MagicMock()
sys.modules['torch'] = mock_torch
