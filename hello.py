import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a greeting.")
    parser.add_argument("name", nargs="?", default="world", help="Name to greet")
    parser.add_argument("-g", "--greeting", default="Hello", help="Greeting to use")
    args = parser.parse_args()

    print(f"{args.greeting}, {args.name}!")


if __name__ == "__main__":
    main()
