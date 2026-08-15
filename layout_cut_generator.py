"""Backward-compatible CLI entrypoint for fabrication_tools.layout."""

from fabrication_tools.layout import main


if __name__ == "__main__":
    raise SystemExit(main())