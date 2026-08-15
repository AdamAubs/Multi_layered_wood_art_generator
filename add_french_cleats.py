"""Backward-compatible CLI entrypoint for fabrication_tools.french_cleats."""

from fabrication_tools.french_cleats import main


if __name__ == "__main__":
    raise SystemExit(main())