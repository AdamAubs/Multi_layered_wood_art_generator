"""Backward-compatible CLI entrypoint for fabrication_tools.trim."""

from fabrication_tools.trim import main


if __name__ == "__main__":
    raise SystemExit(main())