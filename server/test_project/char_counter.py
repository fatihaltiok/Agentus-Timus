import argparse
import json
import sys
import unicodedata
from typing import Dict, List, Tuple, Optional


def count_characters(
    text: str,
    case_sensitive: bool = False,
    include_spaces: bool = False,
) -> Dict[str, int]:
    """
    Count the frequency of each character in ``text``.

    Parameters
    ----------
    text : str
        The input string to analyze.
    case_sensitive : bool, default False
        If ``False``, characters are compared case‑insensitively (converted to lower‑case).
    include_spaces : bool, default False
        If ``False``, all whitespace characters are excluded from the count.

    Returns
    -------
    Dict[str, int]
        A mapping from character to its frequency count.

    Raises
    ------
    ValueError
        If ``text`` is not a string (unlikely due to type hinting).
    """
    if not isinstance(text, str):
        raise ValueError("Input text must be a string.")

    if not case_sensitive:
        text = text.lower()

    counts: Dict[str, int] = {}
    for ch in text:
        if not include_spaces and ch.isspace():
            continue
        counts[ch] = counts.get(ch, 0) + 1

    return counts


def _read_text_from_file(path: str) -> str:
    """
    Read the entire content of a file.

    Parameters
    ----------
    path : str
        Path to the file.

    Returns
    -------
    str
        File content.

    Raises
    ------
    SystemExit
        Exits with a non‑zero status if the file cannot be read.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    except PermissionError:
        print(f"Error: Permission denied: {path}", file=sys.stderr)
        sys.exit(1)
    except UnicodeDecodeError as e:
        print(f"Error: Unicode decode error in file {path}: {e}", file=sys.stderr)
        sys.exit(1)


def _sorted_items(
    counts: Dict[str, int],
    sort_by: str,
    reverse: bool,
) -> List[Tuple[str, int]]:
    """
    Sort the character counts.

    Parameters
    ----------
    counts : Dict[str, int]
        Frequency map.
    sort_by : str
        Either ``'count'`` or ``'char'``.
    reverse : bool
        Whether to sort in descending order.

    Returns
    -------
    List[Tuple[str, int]]
        Sorted list of (character, count) tuples.
    """
    if sort_by == "count":
        return sorted(counts.items(), key=lambda item: item[1], reverse=reverse)
    else:  # sort_by == 'char'
        return sorted(counts.items(), key=lambda item: item[0], reverse=reverse)


def _display_char(ch: str) -> str:
    """
    Return a readable representation of a character for table output.

    Parameters
    ----------
    ch : str
        Single character.

    Returns
    -------
    str
        Human‑readable name.
    """
    if ch.isspace():
        space_names = {
            " ": "SPACE",
            "\t": "TAB",
            "\n": "NEWLINE",
            "\r": "CARRIAGE_RETURN",
            "\v": "VERTICAL_TAB",
            "\f": "FORM_FEED",
        }
        return space_names.get(ch, "WHITESPACE")
    try:
        return unicodedata.name(ch)
    except ValueError:
        return f"U+{ord(ch):04X}"


def _parse_arguments() -> argparse.Namespace:
    """
    Parse command‑line arguments.

    Returns
    -------
    argparse.Namespace
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Character frequency counter with optional JSON output."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text", type=str, help="Input text string.")
    group.add_argument("--file", type=str, help="Path to input file.")
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Treat uppercase and lowercase letters as distinct.",
    )
    parser.add_argument(
        "--include-spaces",
        action="store_true",
        help="Include whitespace characters in the count.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Limit output to top N characters (N >= 1).",
    )
    parser.add_argument(
        "--sort-by",
        choices=["count", "char"],
        default="count",
        help="Sort by count or character.",
    )
    parser.add_argument(
        "--reverse",
        action="store_true",
        help="Reverse sort order.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON.",
    )
    return parser.parse_args()


def main() -> None:
    """
    Entry point for the CLI. Parses arguments, performs character counting,
    sorts results, and prints output in the requested format.
    """
    args = _parse_arguments()

    # Determine default reverse behavior based on sort_by
    if args.sort_by == "count":
        default_reverse = True
    else:
        default_reverse = False

    reverse = args.reverse if args.reverse else default_reverse

    # Validate top N
    if args.top is not None and args.top < 1:
        print("Error: --top must be >= 1.", file=sys.stderr)
        sys.exit(1)

    # Load text
    if args.text is not None:
        text = args.text
    else:  # args.file is not None
        text = _read_text_from_file(args.file)

    # Count characters
    try:
        counts = count_characters(
            text, case_sensitive=args.case_sensitive, include_spaces=args.include_spaces
        )
    except Exception as e:
        print(f"Error during counting: {e}", file=sys.stderr)
        sys.exit(1)

    # Sort items
    sorted_items = _sorted_items(counts, sort_by=args.sort_by, reverse=reverse)

    # Apply top N limit
    if args.top is not None:
        sorted_items = sorted_items[: args.top]

    # Output
    if args.json:
        # Convert sorted items back to dict for JSON output
        json_output = {char: count for char, count in sorted_items}
        print(json.dumps(json_output, ensure_ascii=False, indent=2))
    else:
        # Human‑readable table
        header = f"{'Char':<20} {'CodePoint':<10} {'Count':>5}"
        print(header)
        print("-" * len(header))
        for char, count in sorted_items:
            display = _display_char(char)
            codepoint = f"U+{ord(char):04X}"
            print(f"{display:<20} {codepoint:<10} {count:>5}")


if __name__ == "__main__":
    main()