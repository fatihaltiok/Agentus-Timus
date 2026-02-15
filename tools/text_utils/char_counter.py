import argparse
import sys
from pathlib import Path
from typing import Dict, Iterable, Optional

import unicodedata


def count_characters(
    text: str,
    include_spaces: bool = True,
    include_newlines: bool = True,
    case_sensitive: bool = True,
    normalize: Optional[str] = None,
) -> int:
    """
    Count the number of characters in *text* according to the given options.

    Parameters
    ----------
    text : str
        The input string to be processed.
    include_spaces : bool, default True
        Whether to count space characters (' ').
    include_newlines : bool, default True
        Whether to count newline characters ('\\n' and '\\r').
    case_sensitive : bool, default True
        If False, characters are case-folded before counting.
    normalize : Optional[str], default None
        Unicode normalization form to apply. Must be one of
        'NFC', 'NFD', 'NFKC', 'NFKD'.

    Returns
    -------
    int
        The total number of characters after applying the filters.

    Raises
    ------
    ValueError
        If *normalize* is not None and not a valid normalization form.
    """
    if normalize is not None:
        try:
            text = unicodedata.normalize(normalize, text)
        except Exception as exc:
            raise ValueError(f"Invalid normalization form '{normalize}': {exc}") from exc

    if not case_sensitive:
        text = text.casefold()

    # Filter based on include_spaces and include_newlines
    if not include_spaces:
        text = text.replace(" ", "")
    if not include_newlines:
        text = text.replace("\n", "").replace("\r", "")

    return len(text)


def character_frequencies(
    text: str,
    include_spaces: bool = True,
    include_newlines: bool = True,
    case_sensitive: bool = True,
    normalize: Optional[str] = None,
) -> Dict[str, int]:
    """
    Compute the frequency of each character in *text* according to the given options.

    Parameters
    ----------
    text : str
        The input string to be processed.
    include_spaces : bool, default True
        Whether to count space characters (' ').
    include_newlines : bool, default True
        Whether to count newline characters ('\\n' and '\\r').
    case_sensitive : bool, default True
        If False, characters are case-folded before counting.
    normalize : Optional[str], default None
        Unicode normalization form to apply. Must be one of
        'NFC', 'NFD', 'NFKC', 'NFKD'.

    Returns
    -------
    Dict[str, int]
        Mapping from character to its occurrence count.
    """
    if normalize is not None:
        try:
            text = unicodedata.normalize(normalize, text)
        except Exception as exc:
            raise ValueError(f"Invalid normalization form '{normalize}': {exc}") from exc

    if not case_sensitive:
        text = text.casefold()

    if not include_spaces:
        text = text.replace(" ", "")
    if not include_newlines:
        text = text.replace("\n", "").replace("\r", "")

    freq: Dict[str, int] = {}
    for ch in text:
        freq[ch] = freq.get(ch, 0) + 1

    return freq


def _read_input(
    text_arg: Optional[str],
    file_arg: Optional[str],
) -> str:
    """
    Resolve the input source: direct text, file, or stdin.

    Raises
    ------
    SystemExit
        If both *text_arg* and *file_arg* are provided, or if the file cannot be read.
    """
    if text_arg is not None and file_arg is not None:
        print("Error: Provide either --text or --file, not both.", file=sys.stderr)
        sys.exit(2)

    if text_arg is not None:
        return text_arg

    if file_arg is not None:
        try:
            return Path(file_arg).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"Error reading file '{file_arg}': {exc}", file=sys.stderr)
            sys.exit(2)

    # Read from stdin
    return sys.stdin.read()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Count characters in a text with various options."
    )
    parser.add_argument(
        "--text",
        type=str,
        help="Direct input text to process.",
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Path to a file whose contents will be processed.",
    )
    parser.add_argument(
        "--ignore-spaces",
        dest="include_spaces",
        action="store_false",
        help="Exclude space characters (' ') from counting.",
    )
    parser.add_argument(
        "--no-spaces",
        dest="include_spaces",
        action="store_false",
        help="Alias for --ignore-spaces.",
    )
    parser.add_argument(
        "--ignore-whitespace",
        dest="ignore_whitespace",
        action="store_true",
        help="Exclude all whitespace characters (including tabs, newlines, etc.).",
    )
    parser.add_argument(
        "--ignore-newlines",
        dest="include_newlines",
        action="store_false",
        help="Exclude newline characters ('\\n' and '\\r') from counting.",
    )
    parser.add_argument(
        "--case-insensitive",
        dest="case_sensitive",
        action="store_false",
        help="Ignore case when counting characters.",
    )
    parser.add_argument(
        "--normalize",
        type=str,
        choices=["NFC", "NFD", "NFKC", "NFKD"],
        help="Apply Unicode normalization form to the input.",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Show a sorted frequency table after the total count.",
    )

    args = parser.parse_args()

    # Resolve input text
    raw_text = _read_input(args.text, args.file)

    # Apply ignore_whitespace if requested
    if getattr(args, "ignore_whitespace", False):
        raw_text = "".join(ch for ch in raw_text if not ch.isspace())

    try:
        total = count_characters(
            raw_text,
            include_spaces=args.include_spaces,
            include_newlines=args.include_newlines,
            case_sensitive=args.case_sensitive,
            normalize=args.normalize,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    print(total)

    if args.details:
        freq = character_frequencies(
            raw_text,
            include_spaces=args.include_spaces,
            include_newlines=args.include_newlines,
            case_sensitive=args.case_sensitive,
            normalize=args.normalize,
        )
        # Sort by descending count, then by Unicode codepoint
        sorted_items = sorted(
            freq.items(),
            key=lambda item: (-item[1], ord(item[0])),
        )
        for ch, cnt in sorted_items:
            codepoint = f"U+{ord(ch):04X}"
            print(f"{codepoint} {repr(ch)} {cnt}")


if __name__ == "__main__":
    main()