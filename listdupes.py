#!/usr/bin/env python3

"""Check a folder and its subfolders for duplicate files.

Checks all files except for folders and those starting with a period.
Writes its output to listdupes_output.csv in the user's home folder.
"""

# Module Attributes
__version__ = "3.4.0"
__author__ = "Chris Dobbins"
__license__ = "BSD-2-Clause"


# Modules
import argparse
import collections
import csv
import pathlib
import sys
from zlib import crc32 as checksummer


# Functions
def make_file_path_unique(path):
    """Makes a similarly named Path object if a path already exists.

    Positional Args:
        path: An instance of pathlib.Path or its subclasses.

    Raises:
        FileExistsError after 255 attempts to determine a unique path.

    Returns:
        The value of path, or another Path object with a similar name.
    """

    new_path = None
    for numeric_suffix in range(1, 256):
        if not path.exists() and not new_path:
            return path
        elif not new_path or new_path.exists():
            new_path = pathlib.Path(path.stem + str(numeric_suffix) + path.suffix)
        else:
            return new_path
    raise FileExistsError("A unique path name could not be created.")


def checksum_paths(collection_of_paths):
    paths_and_checksums = []
    for file_path in collection_of_paths:
        try:
            with open(file_path, mode="rb") as file:
                checksum = checksummer(file.read())
        except IsADirectoryError:
            continue  # Skip directories.
        paths_and_checksums.append((file_path, checksum))
    return paths_and_checksums


def find_dupes(paths_and_checksums):
    dupes = collections.defaultdict(list)
    for index, element in enumerate(paths_and_checksums):
        path_being_searched, checksum_being_searched = element

        for current_path, current_checksum in paths_and_checksums[index + 1 :]:
            checksums_are_equal = checksum_being_searched == current_checksum
            if checksums_are_equal and path_not_in_dict(path_being_searched, dupes):
                dupes[path_being_searched].append(current_path)
    return dupes


def path_not_in_dict(path_value, dictionary):
    """Checks if a path exists within a dict's collection values."""
    for paths in dictionary.values():
        if path_value in paths:
            return False
    return True


def write_output_as_csv(output_file, dictionary, open_mode="x"):
    """Writes out the contents of a dict as an Excel style CSV."""
    with open(output_file, mode=open_mode, errors="replace") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["File", "Duplicates"])  # Column labelling row.

        for file, duplicates_list in dictionary.items():
            writer.writerow([file, duplicates_list[0]])
            if len(duplicates_list) > 1:
                for duplicate in duplicates_list[1:]:
                    writer.writerow(["", duplicate])


def handle_exception_at_write_time(exception_info):
    """Prints a message and the exception's traceback. Doesn't exit."""
    error_message = (
        "An error prevented the app from saving its results.\n"
        "To recover the results copy the text below into an empty\n"
        "text file and give it a name that ends with .csv"
    )
    escape_codes = ("\x1b[35m", "\x1b[0m") if sys.stderr.isatty() else ("", "")
    style_magenta, reset_style = escape_codes
    sys.excepthook(*exception_info)  # Prints traceback to stderr.
    print(style_magenta, error_message, reset_style, sep="", file=sys.stderr)


def main():
    # Parse arguments from the shell.
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "starting_folder",
        help="accepts a single path from the terminal",
    )
    args = parser.parse_args()

    # Determine the output's eventual file path.
    output_file_name = "listdupes_output.csv"
    output_path = pathlib.Path("~", output_file_name).expanduser()
    try:
        output_path = make_file_path_unique(output_path)
    except FileExistsError:
        sys.exit("Your home folder has a lot of output files. Clean up to proceed.")

    # Gather all files except for those starting with a period.
    unexpanded_starting_path = pathlib.Path(args.starting_folder)
    starting_path = unexpanded_starting_path.expanduser()
    sub_paths = starting_path.glob("**/[!.]*")

    # Checksum the files.
    files_and_checksums = checksum_paths(sub_paths)

    # Compare the checksums and make a dictionary of duplicate files.
    files_and_checksums.sort()
    dupes = find_dupes(files_and_checksums)

    # Format the duplicate paths as a CSV and write it to a file.
    try:
        write_output_as_csv(output_path, dupes)
    except Exception:  # Print data to stdout if file can't be written.
        handle_exception_at_write_time(sys.exc_info())
        write_output_as_csv(sys.stdout.fileno(), dupes, open_mode="w")
        return 1


# Run the app!
if __name__ == "__main__":
    sys.exit(main())
