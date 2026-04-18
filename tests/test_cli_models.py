"""Tests for models CLI subcommand."""

import json
import pytest
from unittest.mock import patch, MagicMock
from maestro.cli import main


class TestModelsCommand:
    """Tests for maestro models."""

    def test_models_lists_all_providers(self, monkeypatch, capsys):
        """models command lists models from all authenticated providers."""
        mock_models = {
            "chatgpt": ["gpt-5.4", "gpt-4o"],
            "github-copilot": ["gpt-4o", "claude-3-opus"],
        }
        
        with patch("maestro.models.get_available_models", return_value=mock_models):
            with patch("maestro.models.format_model_list") as mock_format:
                mock_format.return_value = "chatgpt:\n  gpt-4o\n  gpt-5.4"
                monkeypatch.setattr("sys.argv", ["maestro", "models"])
                main()
                mock_format.assert_called_once_with(mock_models)

    def test_models_filter_by_provider(self, monkeypatch, capsys):
        """models --provider filters to single provider."""
        mock_models = {
            "chatgpt": ["gpt-5.4", "gpt-4o"],
            "github-copilot": ["gpt-4o"],
        }
        
        with patch("maestro.models.get_available_models", return_value=mock_models):
            with patch("maestro.models.format_model_list") as mock_format:
                mock_format.return_value = "chatgpt:\n  gpt-4o"
                monkeypatch.setattr("sys.argv", ["maestro", "models", "--provider", "chatgpt"])
                main()
                # Should be called with filtered dict
                mock_format.assert_called_once_with({"chatgpt": ["gpt-5.4", "gpt-4o"]})

    def test_models_unknown_provider(self, monkeypatch, capsys):
        """models --provider unknown shows error."""
        with patch("maestro.models.get_available_models", return_value={}):
            with patch("maestro.providers.registry.list_providers", return_value=["chatgpt"]):
                monkeypatch.setattr("sys.argv", ["maestro", "models", "--provider", "unknown"])
                
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 1
        
        captured = capsys.readouterr()
        assert "Unknown provider" in captured.out

    def test_models_provider_not_authenticated(self, monkeypatch, capsys):
        """models --provider for unauthenticated provider shows guidance."""
        with patch("maestro.models.get_available_models", return_value={"chatgpt": ["gpt-4o"]}):
            with patch("maestro.providers.registry.list_providers", return_value=["chatgpt", "github-copilot"]):
                monkeypatch.setattr("sys.argv", ["maestro", "models", "--provider", "github-copilot"])
                
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 1
        
        captured = capsys.readouterr()
        assert "no available models" in captured.out.lower() or "require" in captured.out.lower()

    def test_models_no_providers_authenticated(self, monkeypatch, capsys):
        """models with no authenticated providers shows guidance."""
        with patch("maestro.models.get_available_models", return_value={}):
            monkeypatch.setattr("sys.argv", ["maestro", "models"])
            
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        
        captured = capsys.readouterr()
        assert "authenticate" in captured.out.lower() or "login" in captured.out.lower()


class TestModelsCheck:
    """Tests for maestro models --check."""

    def test_models_check_requires_auth(self, monkeypatch, tmp_path, capsys):
        """models --check requires ChatGPT authentication."""
        # Mock auth.load to return None (not logged in)
        with patch("maestro.cli.auth.load", return_value=None):
            monkeypatch.setattr("sys.argv", ["maestro", "models", "--check"])
            
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1
        
        captured = capsys.readouterr()
        assert "Not logged in" in captured.out

    def test_models_check_success(self, monkeypatch, capsys):
        """models --check probes models when authenticated."""
        mock_ts = MagicMock()
        mock_ts.email = "test@example.com"
        
        all_models = ["gpt-4o", "gpt-5.4"]
        available = ["gpt-4o"]
        
        with patch("maestro.cli.auth.load", return_value=mock_ts):
            with patch("maestro.cli.auth.ensure_valid", return_value=mock_ts):
                with patch("maestro.providers.chatgpt.probe_available_models", return_value=available):
                    with patch("maestro.providers.chatgpt.fetch_models", return_value=all_models):
                        monkeypatch.setattr("sys.argv", ["maestro", "models", "--check"])
                        main()
        
        captured = capsys.readouterr()
        assert "Probing" in captured.out
        assert "gpt-4o" in captured.out
        assert "1/2" in captured.out  # 1 of 2 models available


class TestModelsRefresh:
    """Tests for maestro models --refresh."""

    def test_models_refresh(self, monkeypatch, capsys):
        """models --refresh fetches fresh model catalog."""
        mock_models = {"chatgpt": ["gpt-4o"]}
        
        with patch("maestro.providers.chatgpt.fetch_models") as mock_fetch:
            with patch("maestro.models.get_available_models", return_value=mock_models):
                with patch("maestro.models.format_model_list", return_value="chatgpt:\n  gpt-4o"):
                    monkeypatch.setattr("sys.argv", ["maestro", "models", "--refresh"])
                    main()
                    mock_fetch.assert_called_once_with(force=True)
        
        captured = capsys.readouterr()
        assert "Refreshing" in captured.out
