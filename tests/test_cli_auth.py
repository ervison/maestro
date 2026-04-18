"""Tests for auth CLI subcommands."""

import json
import pytest
import warnings
from unittest.mock import patch, MagicMock
from maestro.cli import main


class TestAuthLogin:
    """Tests for maestro auth login."""

    def test_auth_login_chatgpt_browser(self, monkeypatch):
        """auth login chatgpt uses browser flow by default."""
        mock_ts = MagicMock()
        mock_ts.email = "test@example.com"
        mock_ts.account_id = "acc_123"
        
        with patch("maestro.cli.auth.login", return_value=mock_ts) as mock_login:
            monkeypatch.setattr("sys.argv", ["maestro", "auth", "login", "chatgpt"])
            main()
            mock_login.assert_called_once_with("browser")

    def test_auth_login_chatgpt_device(self, monkeypatch):
        """auth login chatgpt --device uses device code flow."""
        mock_ts = MagicMock()
        mock_ts.email = "test@example.com"
        mock_ts.account_id = "acc_123"
        
        with patch("maestro.cli.auth.login", return_value=mock_ts) as mock_login:
            monkeypatch.setattr("sys.argv", ["maestro", "auth", "login", "chatgpt", "--device"])
            main()
            mock_login.assert_called_once_with("device")

    def test_auth_login_unknown_provider(self, monkeypatch, capsys):
        """auth login unknown-provider shows error."""
        monkeypatch.setattr("sys.argv", ["maestro", "auth", "login", "unknown-provider"])
        
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
        
        captured = capsys.readouterr()
        assert "Unknown provider" in captured.out or "unknown-provider" in captured.out


class TestAuthLogout:
    """Tests for maestro auth logout."""

    def test_auth_logout_success(self, monkeypatch, capsys):
        """auth logout removes credentials when logged in."""
        with patch("maestro.cli.auth.remove", return_value=True) as mock_remove:
            with patch("maestro.providers.registry.list_providers", return_value=["chatgpt"]):
                with patch("maestro.cli.auth.all_providers", return_value=[]):
                    monkeypatch.setattr("sys.argv", ["maestro", "auth", "logout", "chatgpt"])
                    main()
                    mock_remove.assert_called_once_with("chatgpt")
        
        captured = capsys.readouterr()
        assert "Logged out" in captured.out

    def test_auth_logout_not_logged_in(self, monkeypatch, capsys):
        """auth logout shows error when not logged in."""
        with patch("maestro.cli.auth.remove", return_value=False) as mock_remove:
            with patch("maestro.providers.registry.list_providers", return_value=["chatgpt"]):
                with patch("maestro.cli.auth.all_providers", return_value=[]):
                    monkeypatch.setattr("sys.argv", ["maestro", "auth", "logout", "chatgpt"])
                    
                    with pytest.raises(SystemExit) as exc:
                        main()
                    assert exc.value.code == 1
                    mock_remove.assert_called_once_with("chatgpt")
        
        captured = capsys.readouterr()
        assert "Not logged in" in captured.out

    def test_auth_logout_unknown_provider(self, monkeypatch, capsys):
        """auth logout unknown-provider shows error."""
        with patch("maestro.providers.registry.list_providers", return_value=["chatgpt"]):
            with patch("maestro.cli.auth.all_providers", return_value=[]):
                monkeypatch.setattr("sys.argv", ["maestro", "auth", "logout", "unknown"])
                
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 1
        
        captured = capsys.readouterr()
        assert "Unknown provider" in captured.out


class TestAuthStatus:
    """Tests for maestro auth status."""

    def test_auth_status_no_providers(self, monkeypatch, capsys):
        """auth status with no providers shows message."""
        with patch("maestro.providers.registry.list_providers", return_value=[]):
            monkeypatch.setattr("sys.argv", ["maestro", "auth", "status"])
            
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        
        captured = capsys.readouterr()
        assert "No providers" in captured.out

    def test_auth_status_mixed(self, monkeypatch, capsys):
        """auth status shows authenticated and not authenticated providers."""
        mock_provider = MagicMock()
        mock_provider.is_authenticated.return_value = True
        
        with patch("maestro.providers.registry.list_providers", return_value=["chatgpt"]):
            with patch("maestro.cli.get_provider", return_value=mock_provider):
                monkeypatch.setattr("sys.argv", ["maestro", "auth", "status"])
                main()
        
        captured = capsys.readouterr()
        assert "chatgpt" in captured.out
        assert "authenticated" in captured.out

    def test_auth_status_lists_all_discovered_providers(self, monkeypatch, capsys):
        """auth status reports every discovered provider with its own auth state."""
        authenticated = MagicMock()
        authenticated.is_authenticated.return_value = True
        unauthenticated = MagicMock()
        unauthenticated.is_authenticated.return_value = False

        providers = {
            "chatgpt": authenticated,
            "github-copilot": unauthenticated,
        }

        with patch(
            "maestro.providers.registry.list_providers",
            return_value=["chatgpt", "github-copilot"],
        ):
            with patch("maestro.cli.get_provider", side_effect=providers.__getitem__):
                monkeypatch.setattr("sys.argv", ["maestro", "auth", "status"])
                main()

        captured = capsys.readouterr()
        assert "chatgpt: authenticated" in captured.out
        assert "github-copilot: not authenticated" in captured.out

    def test_auth_status_not_authenticated(self, monkeypatch, capsys):
        """auth status shows not authenticated for providers without credentials."""
        mock_provider = MagicMock()
        mock_provider.is_authenticated.return_value = False
        
        with patch("maestro.providers.registry.list_providers", return_value=["chatgpt"]):
            with patch("maestro.cli.get_provider", return_value=mock_provider):
                monkeypatch.setattr("sys.argv", ["maestro", "auth", "status"])
                main()
        
        captured = capsys.readouterr()
        assert "chatgpt" in captured.out
        assert "not authenticated" in captured.out

    def test_auth_status_provider_error(self, monkeypatch, capsys):
        """auth status handles provider loading errors gracefully."""
        with patch("maestro.providers.registry.list_providers", return_value=["chatgpt"]):
            with patch("maestro.cli.get_provider", side_effect=RuntimeError("boom")):
                monkeypatch.setattr("sys.argv", ["maestro", "auth", "status"])
                main()
        
        captured = capsys.readouterr()
        assert "chatgpt" in captured.out
        assert "error" in captured.out


class TestDeprecatedCommands:
    """Tests for deprecated login/logout commands."""

    def test_deprecated_logout_warns(self, monkeypatch, capsys):
        """maestro logout shows deprecation warning."""
        with patch("maestro.cli.auth.remove", return_value=True) as mock_remove:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                monkeypatch.setattr("sys.argv", ["maestro", "logout"])
                main()
                
                # Check deprecation warning was issued
                deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
                assert len(deprecation_warnings) >= 1
                mock_remove.assert_called_once_with("chatgpt")
        
        captured = capsys.readouterr()
        assert "deprecated" in captured.err.lower()
