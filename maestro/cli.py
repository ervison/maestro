"""CLI entry point for maestro."""

import argparse
import sys
import threading
import time
import warnings
from pathlib import Path

from maestro import auth
from maestro.agent import run
from maestro.multi_agent import run_multi_agent
from maestro.providers.chatgpt import DEFAULT_MODEL
from maestro.providers.registry import get_provider


class _Spinner:
    """A simple terminal spinner for long-running operations."""

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    INTERVAL = 0.08

    def __init__(self, message: str = "Thinking..."):
        self._message = message
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._started = False

    def start(self) -> None:
        if not sys.stdout.isatty():
            return  # Don't show spinner in non-interactive terminals
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
        # Clear the spinner line
        print(f"\r{' ' * (len(self._message) + 4)}\r", end="", flush=True)
        self._started = False

    def _spin(self) -> None:
        i = 0
        while not self._stop_event.is_set():
            frame = self.FRAMES[i % len(self.FRAMES)]
            print(f"\r{frame} {self._message}", end="", flush=True)
            i += 1
            self._stop_event.wait(self.INTERVAL)


def main():
    parser = argparse.ArgumentParser(
        prog="maestro",
        description="LangGraph agent using your ChatGPT Plus/Pro subscription",
    )
    sub = parser.add_subparsers(dest="command")

    # auth
    auth_p = sub.add_parser("auth", help="Authentication management")
    auth_sub = auth_p.add_subparsers(dest="auth_command")

    # auth login
    auth_login_p = auth_sub.add_parser("login", help="Authenticate with a provider")
    auth_login_p.add_argument(
        "provider", nargs="?", default="chatgpt", help="Provider to authenticate with"
    )
    auth_login_p.add_argument(
        "--device", action="store_true", help="Use device code flow (headless)"
    )

    # auth logout
    auth_logout_p = auth_sub.add_parser("logout", help="Log out of a provider")
    auth_logout_p.add_argument("provider", help="Provider to log out of")

    # auth status
    auth_sub.add_parser("status", help="Show authentication status for all providers")

    # login
    login_p = sub.add_parser("login", help="Authenticate with ChatGPT")
    login_p.add_argument(
        "--device", action="store_true", help="Use device code flow (headless)"
    )

    # logout
    sub.add_parser("logout", help="Remove stored credentials")

    # run
    run_p = sub.add_parser("run", help="Run the agent")
    run_p.add_argument("prompt", help="Prompt to send")
    run_p.add_argument(
        "-m",
        "--model",
        default=None,
        help=(
            "Model to use (format: provider_id/model_id). "
            "Run 'maestro models' for list. "
            "When omitted, resolution uses --model > environment/config > "
            f"chatgpt/{DEFAULT_MODEL}."
        ),
    )
    run_p.add_argument(
        "-s", "--system", default=None, help="System prompt / instructions"
    )
    run_p.add_argument(
        "--auto",
        action="store_true",
        help="Skip confirmation prompts for destructive actions",
    )
    run_p.add_argument(
        "--workdir",
        default=None,
        metavar="PATH",
        help="Working directory for file tools (default: current directory)",
    )
    run_p.add_argument(
        "--multi",
        action="store_true",
        help="Run in multi-agent mode (DAG pipeline)",
    )
    run_p.add_argument(
        "--no-aggregate",
        action="store_true",
        help="Skip final aggregation summary in --multi mode",
    )

    # models
    models_p = sub.add_parser("models", help="List available models")
    models_p.add_argument(
        "--check", action="store_true", help="Probe which models work for your account"
    )
    models_p.add_argument(
        "--refresh",
        action="store_true",
        help="Force refresh models from models.dev catalog",
    )
    # Allow filtering models by provider (e.g. --provider github-copilot)
    models_p.add_argument(
        "--provider",
        dest="provider",
        default=None,
        help="Filter models to a specific provider id (e.g. 'github-copilot')",
    )

    # status
    sub.add_parser("status", help="Show auth status")

    # planning
    planning_p = sub.add_parser("planning", help="Planning artifact maintenance")
    planning_sub = planning_p.add_subparsers(dest="planning_command")
    planning_check_p = planning_sub.add_parser(
        "check", help="Check ROADMAP/STATE/summary consistency"
    )
    planning_check_p.add_argument(
        "--root",
        default=".planning",
        help="Planning artifact directory to validate (default: .planning)",
    )

    # discover
    discover_p = sub.add_parser("discover", help="Run SDLC discovery planner")
    discover_p.add_argument("prompt", help="Project description or request")
    discover_p.add_argument(
        "--workdir",
        default=".",
        help="Working directory for spec/ output (default: current directory)",
    )
    discover_p.add_argument(
        "--model",
        default=None,
        help="Model to use in provider/model format (e.g. chatgpt/gpt-4o)",
    )
    discover_p.add_argument(
        "--brownfield",
        action="store_true",
        default=False,
        help="Enable brownfield codebase scan (opt-in)",
    )
    discover_p.add_argument(
        "--gaps-port",
        default=4041,
        type=int,
        help="Port for the gap questionnaire web UI. (default: 4041)",
    )
    discover_p.add_argument(
        "--no-browser",
        action="store_true",
        default=False,
        help="Do not auto-open browser for gap questionnaire.",
    )
    discover_p.add_argument(
        "--no-reflect",
        action="store_true",
        default=False,
        help="Skip iterative quality evaluation after artifact generation.",
    )
    discover_p.add_argument(
        "--reflect-max-cycles",
        type=int,
        default=5,
        metavar="INT",
        help="Maximum reflect loop iterations (default: 5).",
    )

    args = parser.parse_args()

    handlers = {
        "auth": lambda: _handle_auth(args, auth_p),
        "login": lambda: _handle_legacy_login(args),
        "logout": _handle_legacy_logout,
        "models": lambda: _handle_models(args),
        "status": _handle_status,
        "run": lambda: _handle_run(args),
        "discover": lambda: _handle_discover(args),
        "planning": lambda: _handle_planning(args, planning_p),
    }

    handler = handlers.get(args.command)
    if handler:
        handler()
    else:
        parser.print_help()


def _auth_login(args) -> None:
    """Handle `maestro auth login <provider>`."""
    method = "device" if getattr(args, "device", False) else "browser"
    try:
        provider = get_provider(args.provider)
    except ValueError as e:
        print(str(e))
        sys.exit(1)
    if args.provider == "chatgpt":
        provider.login(method)
        ts = auth.get("chatgpt")
        if ts:
            email = ts.get("email") or ts.get("account_id", "")
            print(f"Logged in as: {email}" if email else "Logged in to chatgpt.")
        else:
            print("Logged in to chatgpt.")
    else:
        provider.login()


def _auth_logout(args) -> None:
    """Handle `maestro auth logout <provider>`."""
    from maestro.providers.registry import list_providers

    discovered = set(list_providers())
    stored = set(auth.all_providers())
    known = discovered | stored

    if args.provider not in known:
        print(f"Unknown provider: '{args.provider}'")
        print(
            "Available providers: "
            f"{', '.join(sorted(known)) or '(none installed)'}"
        )
        sys.exit(1)

    if auth.remove(args.provider):
        print(f"Logged out of {args.provider}.")
    else:
        print(f"Not logged in to {args.provider}.")
        sys.exit(1)


def _auth_status() -> None:
    """Handle `maestro auth status`."""
    from maestro.providers.registry import list_providers

    discovered = list_providers()
    stored = set(auth.all_providers())
    all_known = sorted(set(discovered) | stored)

    if not all_known:
        print("No providers installed.")
        sys.exit(0)

    print("Provider Status:")
    for pid in all_known:
        if pid in discovered:
            try:
                provider = get_provider(pid)
                if provider.is_authenticated():
                    print(f"  {pid}: authenticated")
                else:
                    print(f"  {pid}: not authenticated")
            except Exception:
                print(f"  {pid}: error loading provider")
        else:
            print(f"  {pid}: credentials stored (provider not installed)")


def _handle_auth(args, auth_p) -> None:
    """Handle `maestro auth` subcommands (login / logout / status)."""
    if args.auth_command == "login":
        _auth_login(args)
    elif args.auth_command == "logout":
        _auth_logout(args)
    elif args.auth_command == "status":
        _auth_status()
    else:
        auth_p.print_help()


def _handle_legacy_login(args) -> None:
    """Handle deprecated `maestro login` command."""
    print(
        "'maestro login' is deprecated. Use 'maestro auth login chatgpt' instead.",
        file=sys.stderr,
    )
    warnings.warn(
        "'maestro login' is deprecated. Use 'maestro auth login chatgpt' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    method = "device" if args.device else "browser"
    ts = auth.login(method)
    print(f"Logged in as: {ts.email or ts.account_id}")


def _handle_legacy_logout() -> None:
    """Handle deprecated `maestro logout` command."""
    print(
        "'maestro logout' is deprecated. Use 'maestro auth logout chatgpt' instead.",
        file=sys.stderr,
    )
    warnings.warn(
        "'maestro logout' is deprecated. Use 'maestro auth logout chatgpt' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    if auth.remove("chatgpt"):
        print("Logged out of chatgpt.")
    else:
        print("Not logged in to chatgpt.")


def _models_probe_mode(args) -> None:
    """Handle `maestro models --check` probe path."""
    from maestro.providers.chatgpt import fetch_models, probe_available_models

    provider_label = getattr(args, "provider", None) or "chatgpt"
    print(
        "Probing models for provider: "
        f"{provider_label} (this may take a moment)..."
    )
    ts = auth.load()
    if not ts:
        print("Not logged in to ChatGPT.")
        sys.exit(1)
    ts = auth.ensure_valid(ts)
    available = probe_available_models(ts, force=True)
    all_models = fetch_models()
    for m in all_models:
        if m in available:
            print(f"  chatgpt/{m}  [available]")
        else:
            print(f"  chatgpt/{m}  [not available]")
    print(f"\n{len(available)}/{len(all_models)} models available.")


def _models_filter_provider(args, models_by_provider: dict) -> dict:
    """Filter models_by_provider to a single provider, or exit on error."""
    from maestro.providers.registry import list_providers

    provider_models = models_by_provider.get(args.provider)
    if provider_models:
        return {args.provider: provider_models}

    discovered = list_providers()
    if args.provider in discovered:
        print(f"Provider '{args.provider}' has no available models.")
        print(
            "(Provider may require authentication: "
            f"maestro auth login {args.provider})"
        )
    else:
        print(f"Unknown provider: '{args.provider}'")
        available = (
            ", ".join(sorted(discovered)) if discovered else "(none installed)"
        )
        print(f"Available providers: {available}")
    sys.exit(1)


def _handle_models(args) -> None:
    """Handle `maestro models` command."""
    from maestro.models import get_available_models, format_model_list
    from maestro.providers.chatgpt import fetch_models

    if args.refresh:
        print("Refreshing models from models.dev...")
        fetch_models(force=True)

    if args.provider and args.check:
        print("Error: --check cannot be combined with --provider.")
        sys.exit(1)

    if args.check:
        _models_probe_mode(args)
        return

    models_by_provider = get_available_models()

    if args.provider:
        models_by_provider = _models_filter_provider(args, models_by_provider)

    models_by_provider = {
        provider_id: models
        for provider_id, models in models_by_provider.items()
        if models
    }

    if not models_by_provider:
        print("No models available. Authenticate a provider first:")
        print("  maestro auth login chatgpt")
        sys.exit(0)

    print(format_model_list(models_by_provider))


def _handle_status() -> None:
    """Handle `maestro status` command."""
    ts = auth.load()
    if not ts:
        print("Not logged in.")
        sys.exit(1)
    print(f"Email:      {ts.email or '(unknown)'}")
    print(f"Account ID: {ts.account_id}")
    remaining = ts.expires - time.time()
    if remaining > 0:
        print(f"Token:      valid ({int(remaining)}s remaining)")
    else:
        print("Token:      expired (will refresh on next use)")


def _handle_run(args) -> None:
    """Handle `maestro run` command (single-agent and multi-agent modes)."""
    import os

    from maestro.models import resolve_model
    from maestro.config import load as load_config

    wd = Path(args.workdir).resolve() if args.workdir else Path.cwd()

    model_id: str | None = None
    try:
        provider, model_id = resolve_model(model_flag=args.model)

        if args.model is not None:
            selected_explicitly = True
        elif os.environ.get("MAESTRO_MODEL") is not None:
            selected_explicitly = True
        else:
            cfg = load_config()
            selected_explicitly = cfg.model is not None

        if provider.id != "chatgpt" and not selected_explicitly:
            provider = get_provider("chatgpt")
            model_id = DEFAULT_MODEL

        if args.multi:
            _handle_run_multi(args, wd, provider, model_id)
        else:
            _handle_run_single(args, wd, provider, model_id)

    except (RuntimeError, ValueError) as e:
        msg = str(e)
        if "not supported" in msg and model_id is not None:
            print(f"Error: model '{model_id}' is not available for your account.")
            print("Run 'maestro models --check' to see which models work for you.")
        else:
            print(f"Error: {msg}")
        sys.exit(1)


def _handle_run_multi(args, wd, provider, model_id) -> None:
    """Handle `maestro run --multi` DAG execution."""
    import os
    import time as _time
    from maestro.dashboard.emitter import DashboardEmitter
    from maestro.dashboard.server import start_dashboard_server

    aggregate = False if args.no_aggregate else None

    dashboard_emitter = DashboardEmitter()
    dashboard_port = int(os.environ.get("MAESTRO_DASHBOARD_PORT", "4040"))
    start_dashboard_server(dashboard_emitter, port=dashboard_port)
    print(f"[maestro] dashboard → http://localhost:{dashboard_port}")

    result = run_multi_agent(
        task=args.prompt,
        workdir=wd,
        auto=args.auto,
        depth=0,
        max_depth=2,
        provider=provider,
        model=model_id,
        aggregate=aggregate,
        emitter=dashboard_emitter,
    )

    outputs = result.get("outputs", {})
    failed = result.get("failed", [])
    errors = result.get("errors", [])

    if errors:
        print("\n--- Worker Errors ---", file=sys.stderr)
        for err in errors:
            print(err, file=sys.stderr)

    if not outputs:
        print("Error: No workers completed successfully.", file=sys.stderr)
        sys.exit(1)

    if "summary" in result:
        print("\n--- Final Summary ---")
        print(result["summary"])
    else:
        print("\n--- Worker Outputs ---")
        for task_id, output in outputs.items():
            print(f"\n[{task_id}]:\n{output}")

    _time.sleep(2)

    if failed:
        sys.exit(1)


def _handle_run_single(args, wd, provider, model_id) -> None:
    """Handle `maestro run` single-agent mode."""
    streamed: list[bool] = []
    spinner = _Spinner()
    spinner.start()

    def _stream_print(chunk: str) -> None:
        spinner.stop()
        print(chunk, end="", flush=True)
        streamed.append(True)

    def _on_tool_start() -> None:
        spinner.stop()

    result = run(
        model_id,
        args.prompt,
        args.system,
        workdir=wd,
        auto=args.auto,
        provider=provider,
        stream_callback=_stream_print,
        on_tool_start=_on_tool_start,
    )
    spinner.stop()
    if not streamed:
        print(result)
    else:
        print()


def _handle_discover(args) -> None:
    """Handle the `maestro discover` subcommand."""
    from maestro.sdlc import DiscoveryHarness, SDLCRequest
    from maestro.models import resolve_model

    try:
        request = SDLCRequest(
            prompt=args.prompt,
            brownfield=getattr(args, "brownfield", False),
            workdir=getattr(args, "workdir", "."),
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        provider, model_id = resolve_model(model_flag=getattr(args, "model", None))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(
        f"Starting SDLC discovery using model: {model_id or 'default'}\n"
        "Generating 13 artifacts.\n"
        f"  If gaps are found, a questionnaire will open at http://localhost:{getattr(args, 'gaps_port', 4041)}\n"
        "  Answer all questions and click Submit to continue.\n",
        file=sys.stderr,
        flush=True,
    )

    harness = DiscoveryHarness(
        provider=provider,
        model=model_id,
        workdir=request.workdir,
        gaps_port=getattr(args, "gaps_port", 4041),
        open_browser=not getattr(args, "no_browser", False),
        reflect=not getattr(args, "no_reflect", False),
        reflect_max_cycles=getattr(args, "reflect_max_cycles", 5),
    )
    result = harness.run(request)
    print(f"\n✓ {result.artifact_count} artifacts written to {result.spec_dir}")


def _handle_planning_check(args) -> None:
    """Handle `maestro planning check`."""
    from maestro.planning import check_planning_consistency

    result = check_planning_consistency(getattr(args, "root", ".planning"))
    if result.errors:
        print("Planning consistency check failed:", file=sys.stderr)
        for error in result.errors:
            print(f"- {error}", file=sys.stderr)
        sys.exit(1)

    print(
        f"Planning consistency check passed for {Path(getattr(args, 'root', '.planning')).resolve()}"
    )
    sys.exit(0)


def _handle_planning(args, planning_p) -> None:
    """Route `maestro planning` subcommands."""
    if args.planning_command == "check":
        _handle_planning_check(args)
    else:
        planning_p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
