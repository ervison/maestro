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
    auth_login_p = auth_sub.add_parser("login", help="Authenticate with a provider")
    auth_login_p.add_argument(
        "provider", nargs="?", default="chatgpt", help="Provider to authenticate with"
    )
    auth_login_p.add_argument(
        "--device", action="store_true", help="Use device code flow (headless)"
    )

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
        auth.logout()

    elif args.command == "models":
        if args.check:
            from langchain_core.messages import HumanMessage
            from maestro.agent import _call_responses_api

            ts = auth.load()
            if not ts:
                print("Not logged in.")
                sys.exit(1)
            ts = auth.ensure_valid(ts)
            msgs = [HumanMessage(content="hi")]
            print("Probing models (this may take a moment)...")
            for m in auth.MODELS:
                try:
                    _call_responses_api(m, msgs, ts)
                    print(f"  {m}  [available]")
                except RuntimeError as e:
                    msg = str(e)
                    if "not supported" in msg:
                        print(f"  {m}  [not available for your account]")
                    else:
                        print(f"  {m}  [error: {msg[:60]}]")
        else:
            print(f"Default: {auth.DEFAULT_MODEL}")
            print("Models (use -m <name> to select):")
            for m in auth.MODELS:
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
