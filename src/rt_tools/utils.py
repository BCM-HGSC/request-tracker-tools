"""Utility functions for RT tools."""


def remove_fixed_string(multiline_string: str, fixed_string: str) -> str:
    """Remove a fixed string from each line of a multiline string."""
    lines = multiline_string.splitlines()
    cleaned_lines = [line.replace(fixed_string, "") for line in lines]
    return "\n".join(cleaned_lines)
