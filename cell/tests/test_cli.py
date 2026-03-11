from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from cell.config import load_cell_config
from cellforge import cli


@pytest.mark.asyncio
async def test_doctor_attempts_temporal_autofix(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    async def fake_ensure_local_stack(host: str) -> tuple[bool, str]:
        assert host == "localhost:7233"
        return True, "Started local Temporal stack with docker compose.\nTemporal reachable at localhost:7233"

    monkeypatch.setattr(cli, "ensure_local_stack", fake_ensure_local_stack)
    monkeypatch.setattr(cli, "provider_checks", lambda cfg: [("executor", "OK", "claude via Anthropic", [])])

    result = await cli.doctor_command(
        Namespace(
            config=str(Path(__file__).resolve().parents[1] / "configs" / "default_cell.yaml"),
            host="localhost:7233",
            no_fix=False,
        )
    )

    captured = capsys.readouterr().out
    assert result == 0
    assert "Started local Temporal stack with docker compose" in captured


def test_provider_checks_report_missing_anthropic_key_actionably(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = load_cell_config(Path(__file__).resolve().parents[1] / "configs" / "default_cell.yaml")

    checks = cli.provider_checks(cfg)

    executor_check = next(item for item in checks if item[0] == "executor")
    assert executor_check[1] == "FAIL"
    assert "missing ANTHROPIC_API_KEY" in executor_check[2]
    assert any("export ANTHROPIC_API_KEY=your_key" in hint for hint in executor_check[3])
    assert any("Supported alternates:" in hint for hint in executor_check[3])
