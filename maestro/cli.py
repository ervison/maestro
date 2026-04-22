"""CLI entry point for maestro."""

import argparse
import sys
import threading
import time
import warnings

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

    args = parser.parse_args()

    if args.command == "auth":
        if args.auth_command == "login":
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

        elif args.auth_command == "logout":
            from maestro.providers.registry import list_providers

            # Validate provider exists (discovered or has stored credentials)
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

        elif args.auth_command == "status":
            from maestro.providers.registry import list_providers

            discovered = list_providers()
            stored = set(auth.all_providers())

            # Union: show discovered providers + any stored-but-undiscoverable
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
                    # Stored credentials but provider not installed
                    print(f"  {pid}: credentials stored (provider not installed)")

        else:
            auth_p.print_help()

    elif args.command == "login":
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

    elif args.command == "logout":
        print(
            (
                "'maestro logout' is deprecated. "
                "Use 'maestro auth logout chatgpt' instead."
            ),
            file=sys.stderr,
        )
        warnings.warn(
            (
                "'maestro logout' is deprecated. "
                "Use 'maestro auth logout chatgpt' instead."
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        if auth.remove("chatgpt"):
            print("Logged out of chatgpt.")
        else:
            print("Not logged in to chatgpt.")

    elif args.command == "models":
        from maestro.models import get_available_models, format_model_list
        from maestro.providers.registry import list_providers
        from maestro.providers.chatgpt import fetch_models, probe_available_models

        if args.refresh:
            print("Refreshing models from models.dev...")
            fetch_models(force=True)

        if args.provider and args.check:
            print("Error: --check cannot be combined with --provider.")
            sys.exit(1)

        if args.check:
            # Announce which provider's probe is being used. By default we
            # use the ChatGPT/Responses API probe. (If provider-specific
            # probing is later added, this printed label should reflect that.)
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
            return

        # Multi-provider listing
        models_by_provider = get_available_models()

        if args.provider:
            # Filter to single provider
            provider_models = models_by_provider.get(args.provider)
            if provider_models is None or not provider_models:
                # Provider not in dict or has empty list
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
                        ", ".join(sorted(discovered))
                        if discovered
                        else "(none installed)"
                    )
                    print(f"Available providers: {available}")
                sys.exit(1)
            models_by_provider = {args.provider: provider_models}

        # Filter out providers with empty model lists
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

    elif args.command == "status":
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

    elif args.command == "run":
        import os
        from pathlib import Path

        from maestro.models import resolve_model
        from maestro.config import load as load_config

        wd = Path(args.workdir).resolve() if args.workdir else Path.cwd()

        try:
            # Resolve model using Phase 4 resolution chain
            # (flag > env > config > default)
            provider, model_id = resolve_model(model_flag=args.model)

            if args.model is not None:
                selected_explicitly = True
            elif os.environ.get("MAESTRO_MODEL") is not None:
                selected_explicitly = True
            else:
                cfg = load_config()
                selected_explicitly = cfg.model is not None

            # Phase 5 will wire alternate providers; for now,
            # pin to ChatGPT unless explicitly requested.
            if provider.id != "chatgpt" and not selected_explicitly:
                # Default resolution picked a non-ChatGPT provider,
                # but user didn't explicitly request it.
                # Fall back to ChatGPT to maintain backward compatibility
                # until Phase 5.
                provider = get_provider("chatgpt")
                model_id = DEFAULT_MODEL

            if args.multi:
                # Multi-agent DAG mode
                # Only pass False when --no-aggregate is present; otherwise pass None
                # so runtime config can decide (config.aggregator.enabled)
                aggregate = False if args.no_aggregate else None

                import os
                from maestro.dashboard.emitter import DashboardEmitter
                from maestro.dashboard.server import start_dashboard_server

                dashboard_emitter = DashboardEmitter()
                dashboard_port = int(os.environ.get("MAESTRO_DASHBOARD_PORT", "4040"))
                start_dashboard_server(dashboard_emitter, port=dashboard_port)
                print(f"[maestro] dashboard → http://localhost:{dashboard_port}")

                result = run_multi_agent(
                    task=args.prompt,
                    workdir=wd,
                    auto=args.auto,
                    depth=0,  # CLI starts at depth 0
                    max_depth=2,  # Default max_depth
                    provider=provider,
                    model=model_id,
                    aggregate=aggregate,
                    emitter=dashboard_emitter,
                )

                # Extract outputs and failure metadata from structured result
                outputs = result.get("outputs", {})
                failed = result.get("failed", [])
                errors = result.get("errors", [])

                # Always surface worker errors first (even when all workers fail)
                if errors:
                    print("\n--- Worker Errors ---", file=sys.stderr)
                    for err in errors:
                        print(err, file=sys.stderr)

                if not outputs:
                    print("Error: No workers completed successfully.", file=sys.stderr)
                    sys.exit(1)

                # Print summary if available
                if "summary" in result:
                    print("\n--- Final Summary ---")
                    print(result["summary"])
                else:
                    # Aggregation was skipped, print outputs
                    print("\n--- Worker Outputs ---")
                    for task_id, output in outputs.items():
                        print(f"\n[{task_id}]:\n{output}")

                # Give the SSE server time to flush final events to the browser
                # before the daemon thread is killed by process exit
                import time as _time
                _time.sleep(2)

                # Surface worker failures after outputs
                if failed:
                    sys.exit(1)
            else:
                # Single-agent mode (original behavior)
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
                spinner.stop()  # ensure stopped if no text/tools were seen
                if not streamed:
                    # No streaming chunks received — print the full result at once
                    print(result)
                else:
                    # Streaming already printed the content; just end with a newline
                    print()
        except (RuntimeError, ValueError) as e:
            msg = str(e)
            if "not supported" in msg:
                print(f"Error: model '{model_id}' is not available for your account.")
                print("Run 'maestro models --check' to see which models work for you.")
            else:
                print(f"Error: {msg}")
            sys.exit(1)

    elif args.command == "discover":
        _handle_discover(args)

    else:
        parser.print_help()


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
    )
    result = harness.run(request)
    print(f"\n✓ {result.artifact_count} artifacts written to {result.spec_dir}")


if __name__ == "__main__":
    main()
