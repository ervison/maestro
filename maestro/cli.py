"""CLI entry point for maestro."""

import argparse
import sys
import warnings

from maestro import auth
from maestro.agent import run
from maestro.providers.chatgpt import DEFAULT_MODEL
from maestro.providers.registry import get_provider


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
    auth_logout_p.add_argument(
        "provider", help="Provider to log out of"
    )

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
            "Model to use (format: provider_id/model_id). Run 'maestro models' for list. "
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

    # models
    models_p = sub.add_parser("models", help="List available models")
    models_p.add_argument(
        "--check", action="store_true", help="Probe which models work for your account"
    )
    models_p.add_argument(
        "--refresh", action="store_true", help="Force refresh models from models.dev catalog"
    )

    # status
    sub.add_parser("status", help="Show auth status")

    args = parser.parse_args()

    if args.command == "auth":
        if args.auth_command == "login":
            if args.provider == "chatgpt":
                method = "device" if args.device else "browser"
                ts = auth.login(method)
                print(f"Logged in as: {ts.email or ts.account_id}")
            else:
                try:
                    provider = get_provider(args.provider)
                except ValueError as e:
                    print(str(e))
                    sys.exit(1)
                provider.login()

        elif args.auth_command == "logout":
            from maestro.providers.registry import list_providers

            # Validate provider exists
            discovered = list_providers()
            if args.provider not in discovered:
                print(f"Unknown provider: '{args.provider}'")
                print(f"Available providers: {', '.join(discovered)}")
                sys.exit(1)

            if auth.remove(args.provider):
                print(f"Logged out of {args.provider}.")
            else:
                print(f"Not logged in to {args.provider}.")
                sys.exit(1)

        elif args.auth_command == "status":
            from maestro.providers.registry import list_providers, get_provider

            discovered = list_providers()
            stored = auth.all_providers()

            if not discovered:
                print("No providers installed.")
                sys.exit(0)

            print("Provider Status:")
            for pid in discovered:
                try:
                    provider = get_provider(pid)
                    if provider.is_authenticated():
                        print(f"  {pid}: authenticated")
                    else:
                        print(f"  {pid}: not authenticated")
                except Exception:
                    print(f"  {pid}: error loading provider")

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

    elif args.command == "models":
        from maestro.providers.chatgpt import fetch_models, probe_available_models

        if args.refresh:
            print("Refreshing models from models.dev...")
            fetch_models(force=True)

        if args.check:
            ts = auth.load()
            if not ts:
                print("Not logged in.")
                sys.exit(1)
            ts = auth.ensure_valid(ts)
            print("Probing models (this may take a moment)...")
            available = probe_available_models(ts, force=True)
            all_models = fetch_models()
            for m in all_models:
                if m in available:
                    print(f"  {m}  [available]")
                else:
                    print(f"  {m}  [not available for your account]")
            print(f"\n{len(available)}/{len(all_models)} models available.")
        else:
            # Show only available models (cached probe)
            ts = auth.load()
            if not ts:
                # Not logged in — show full catalog
                models = fetch_models()
                print(f"Default: {auth.DEFAULT_MODEL}")
                print("All known models (login to see which are available):")
                for m in models:
                    marker = " *" if m == auth.DEFAULT_MODEL else ""
                    print(f"  {m}{marker}")
            else:
                ts = auth.ensure_valid(ts)
                available = probe_available_models(ts)
                if not available:
                    print("No cached availability data. Run: maestro models --check")
                    models = fetch_models()
                    print(f"\nAll known models:")
                    for m in models:
                        print(f"  {m}")
                else:
                    print(f"Default: {auth.DEFAULT_MODEL}")
                    print(f"Available models ({len(available)}):")
                    for m in available:
                        marker = " *" if m == auth.DEFAULT_MODEL else ""
                        print(f"  {m}{marker}")

    elif args.command == "status":
        ts = auth.load()
        if not ts:
            print("Not logged in.")
            sys.exit(1)
        print(f"Email:      {ts.email or '(unknown)'}")
        print(f"Account ID: {ts.account_id}")
        import time

        remaining = ts.expires - time.time()
        if remaining > 0:
            print(f"Token:      valid ({int(remaining)}s remaining)")
        else:
            print(f"Token:      expired (will refresh on next use)")

    elif args.command == "run":
        import os
        from pathlib import Path

        from maestro.models import resolve_model
        from maestro.config import load as load_config

        wd = Path(args.workdir).resolve() if args.workdir else Path.cwd()

        try:
            # Resolve model using Phase 4 resolution chain (flag > env > config > default)
            provider, model_id = resolve_model(model_flag=args.model)

            if args.model is not None:
                selected_explicitly = True
            elif os.environ.get("MAESTRO_MODEL") is not None:
                selected_explicitly = True
            else:
                cfg = load_config()
                selected_explicitly = cfg.model is not None

            # Phase 5 will wire alternate providers; for now, pin to ChatGPT unless explicitly requested
            if provider.id != "chatgpt" and not selected_explicitly:
                # Default resolution picked a non-ChatGPT provider, but user didn't explicitly request it
                # Fall back to ChatGPT to maintain backward compatibility until Phase 5
                provider = get_provider("chatgpt")
                model_id = DEFAULT_MODEL

            # Phase 5 will wire alternate providers; for now, reject non-ChatGPT providers
            if provider.id != "chatgpt":
                raise RuntimeError(
                    f"Provider '{provider.id}' is discoverable but not runnable yet; "
                    "Phase 5 must wire provider.stream()"
                )

            result = run(
                model_id, args.prompt, args.system, workdir=wd, auto=args.auto
            )
            print(result)
        except (RuntimeError, ValueError) as e:
            msg = str(e)
            if "not supported" in msg:
                print(f"Error: model '{model_id}' is not available for your account.")
                print("Run 'maestro models --check' to see which models work for you.")
            else:
                print(f"Error: {msg}")
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
