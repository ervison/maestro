"""CLI entry point for maestro."""

import argparse
import sys

from maestro import auth
from maestro.agent import run


def main():
    parser = argparse.ArgumentParser(
        prog="maestro",
        description="LangGraph agent using your ChatGPT Plus/Pro subscription",
    )
    sub = parser.add_subparsers(dest="command")

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
        default=auth.DEFAULT_MODEL,
        help=f"Model to use (default: {auth.DEFAULT_MODEL}). Run 'maestro models' for list.",
    )
    run_p.add_argument("-s", "--system", default=None, help="System prompt")

    # models
    models_p = sub.add_parser("models", help="List available models")
    models_p.add_argument(
        "--check", action="store_true", help="Probe which models work for your account"
    )

    # status
    sub.add_parser("status", help="Show auth status")

    args = parser.parse_args()

    if args.command == "login":
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
        try:
            result = run(args.model, args.prompt, args.system)
            print(result)
        except RuntimeError as e:
            msg = str(e)
            if "not supported" in msg:
                print(f"Error: model '{args.model}' is not available for your account.")
                print("Run 'maestro models --check' to see which models work for you.")
            else:
                print(f"Error: {msg}")
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
