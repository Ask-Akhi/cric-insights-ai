# conftest.py — root pytest configuration
# Adds the repo root to sys.path so "from backend.src.main import app" resolves.
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
