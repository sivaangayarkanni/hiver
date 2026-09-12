#!/usr/bin/env python3
"""Convenience wrapper — prefer: python -m hiver_agent run-pipeline"""
from hiver_agent.cli.main import app

if __name__ == "__main__":
    app(["run-pipeline", "--dry-run", "--limit", "5"])
