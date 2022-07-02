#!/usr/bin/env python3

"""Check a folder and its subfolders for duplicate files.

Checks all files except for folders and those starting with a period.
Writes its output to listdupes_output.csv in the user's home folder.
"""

# Module Attributes
__version__ = "Internal"
__author__ = "Chris Dobbins"
__license__ = "BSD-2-Clause"


# Modules
import argparse
import collections
import csv
import glob
import pathlib
import sys
from zlib import crc32 as checksummer


# Classes
class Cursor:
    """Provides structure to subclasses which write to terminal."""

    hide_cursor = "\x1b[?25l"  # Terminal escape codes.
    show_cursor = "\x1b[?25h"

    def __init__(self, output=sys.stderr):
        self.output = output

    def hide_cursor_from_user(self):
        print(Cursor.hide_cursor, file=self.output, end="")

    def set_cursor_column_to(self, column_number):
        set_cursor_column_esc_code = f"\x1b[{column_number}G"
        print(set_cursor_column_esc_code, file=self.output, end="")


class ProgressCounter(Cursor):
    """Methods for printing the state of an iteration to a terminal."""

    def __init__(
        self,
        total_to_be_counted,
        text_before_counter="",
        text_after_counter="",
        output=sys.stderr,
    ):
        self.total_to_be_counted = total_to_be_counted
        self.text_before_counter = text_before_counter
        self.text_after_counter = text_after_counter
        self.output = output

        # TODO: Address length_of_total only being foolproof if total comes from len().
        self.length_of_total = len(str(total_to_be_counted))
        self.length_of_text_before_counter = len(self.text_before_counter)
        self.length_of_text_after_counter = len(self.text_after_counter)
        self.start_of_counter = self.length_of_text_before_counter + 1
        self.after_counter = (
            self.length_of_text_before_counter + self.length_of_total + 1
        )
        self.after_text = (
            self.length_of_text_before_counter
            + self.length_of_total
            + self.length_of_text_after_counter
        )
        self.move_to_start_of_counter = f"\x1b[{self.start_of_counter}G"

    def print_text_for_counter(self):
        """Convenience method which handles the most typical setup."""
        self.hide_cursor_from_user()
        self.print_text_before_counter()
        self.print_text_after_counter(self.after_counter)
        self.set_cursor_column_to(self.start_of_counter)

    def print_counter(self, current_index):
        """Counter designed to be inserted in loops."""
        counter_value = str(current_index + 1).rjust(self.length_of_total, "0")
        print(
            counter_value,
            self.move_to_start_of_counter,
            file=self.output,
            flush=True,
            sep="",
            end="",
        )

    def print_counter_and_end_count(self, current_index):
        """Convenience method that might be a touch slower."""
        self.print_counter(current_index)
        if (current_index + 1) == self.total_to_be_counted:
            self.end_count()

    def print_text_before_counter(self):
        """Provide context about a counter by printing text before it.

        Prints the value of text_before_counter provided to the class's
        constructor (Defaults to printing no text).
        Example text: 'Checking file '
        """

        print(self.text_before_counter, file=self.output, end="")

    def print_text_after_counter(self, starting_column_for_cursor):
        """Provide context about a counter by printing text after it.

        Prints the value of text_after_counter provided to the class's
        constructor (Defaults to printing no text). If the str provides
        a replacement field the total number of the counter will be
        inserted there.
        Example text: ' of {}.'

        Positional Args:
            starting_column_for_cursor: An int which determines at which
                column the text starts printing
        """

        formatted_text = self.text_after_counter.format(self.total_to_be_counted)
        self.set_cursor_column_to(starting_column_for_cursor)
        print(
            formatted_text,
            sep="",
            file=self.output,
            end="",
        )

    def end_count(self, append_newline=True):
        """Place the cursor at the end of the line and show it."""
        end_arg = "\n" if append_newline else ""
        self.set_cursor_column_to(self.after_text)
        print(self.show_cursor, file=self.output, end=end_arg)


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
    """Checksums files and stores their checksums alongside their paths.

    Positional Args:
        collection_of_paths: A collection of strings, or instances of
            pathlib.Path and its subclasses.

    Returns:
        A list of tuples, each containing a file path and the checksum
            of the corresponding file.
    """

    paths_and_checksums = []
    for file_path in collection_of_paths:
        try:
            with open(file_path, mode="rb") as file:
                checksum = checksummer(file.read())
        except IsADirectoryError:
            continue  # Skip directories.
        paths_and_checksums.append((file_path, checksum))
    return paths_and_checksums


def checksum_paths_and_show_progress(collection_of_paths):
    """As checksum_paths but prints the loop's progress to terminal."""
    checksum_progress = ProgressCounter(
        len(collection_of_paths),
        text_before_counter="Checking file ",
        text_after_counter=" of {}.",
    )
    paths_and_checksums = []
    try:
        checksum_progress.print_text_for_counter()
        for index, file_path in enumerate(collection_of_paths):
            try:
                with open(file_path, mode="rb") as file:
                    checksum = checksummer(file.read())
            except IsADirectoryError:
                continue  # Skip directories.
            paths_and_checksums.append((file_path, checksum))
            checksum_progress.print_counter(index)
    finally:
        checksum_progress.end_count()
    return paths_and_checksums


def find_dupes(paths_and_checksums):
    """Finds duplicate files by comparing their checksums.

    Positional Args:
        paths_and_checksums: A list of tuples, each containing a file
            path and the checksum of the corresponding file.

    Returns:
        A dictionary of paths mapped to sets of any other paths whose
            checksums match the first.
    """

    dupes = collections.defaultdict(set)
    for index, element in enumerate(paths_and_checksums):
        path_being_searched, checksum_being_searched = element

        for current_path, current_checksum in paths_and_checksums[index + 1 :]:
            checksums_are_equal = checksum_being_searched == current_checksum
            if checksums_are_equal and path_not_in_dict(path_being_searched, dupes):
                dupes[path_being_searched].add(current_path)
    return dupes


def find_dupes_and_show_progress(paths_and_checksums):
    """As find_dupes but prints the loop's progress to terminal."""
    comparisons_progress = ProgressCounter(
        len(paths_and_checksums),
        text_before_counter="Comparing file ",
        text_after_counter=" of {}.",
    )
    dupes = collections.defaultdict(set)
    try:
        comparisons_progress.print_text_for_counter()
        for index, element in enumerate(paths_and_checksums):
            path_being_searched, checksum_being_searched = element
            comparisons_progress.print_counter(index)

            for current_path, current_checksum in paths_and_checksums[index + 1 :]:
                checksums_are_equal = checksum_being_searched == current_checksum
                if checksums_are_equal and path_not_in_dict(path_being_searched, dupes):
                    dupes[path_being_searched].add(current_path)
    finally:
        comparisons_progress.end_count()
    return dupes


def path_not_in_dict(path_value, dictionary):
    """Checks if a path exists within a dict's collection values."""
    for paths in dictionary.values():
        if path_value in paths:
            return False
    return True


def sort_dict_values(dictionary, sort_key=None):
    """Convert collections in a dict to lists and sort them in place."""
    for dict_key in dictionary.keys():
        list_of_values = list(dictionary[dict_key])
        list_of_values.sort(key=sort_key)
        dictionary[dict_key] = list_of_values


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
    parser.add_argument(
        "-p",
        "--progress",
        action="store_true",
        help="print a progress counter to stderr, can slow things down",
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
    if args.progress:
        glob_module_arg = str(starting_path) + "/**/[!.]*"
        sub_paths = glob.glob(glob_module_arg, recursive=True)
    else:
        sub_paths = starting_path.glob("**/[!.]*")

    # Checksum the files.
    if args.progress:
        files_and_checksums = checksum_paths_and_show_progress(sub_paths)
    else:
        files_and_checksums = checksum_paths(sub_paths)

    # Compare the checksums and make a dictionary of duplicate files.
    files_and_checksums.sort()
    if args.progress:
        dupes = find_dupes_and_show_progress(files_and_checksums)
    else:
        dupes = find_dupes(files_and_checksums)

    # Sort the duplicates to prepare them for output.
    sort_dict_values(dupes)

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
