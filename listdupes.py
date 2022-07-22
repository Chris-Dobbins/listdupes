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
        collection_to_count,
        text_before_counter="",
        text_after_counter="",
        output=sys.stderr,
    ):
        self.collection_to_count = collection_to_count
        self.text_before_counter = text_before_counter
        self.text_after_counter = text_after_counter
        self.output = output

        self.total_to_be_counted = len(self.collection_to_count)
        self.length_of_total = len(str(self.total_to_be_counted))
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
        self.print_zero_to_counter()

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
        constructor (Defaults to printing no text). If the string
        provides a replacement field the total number of the counter
        will be inserted there.
        Example text: ' of {}.'

        Args:
            starting_column_for_cursor: An integer which determines
                at which column the text starts printing.
        """

        formatted_text = self.text_after_counter.format(self.total_to_be_counted)
        self.set_cursor_column_to(starting_column_for_cursor)
        print(
            formatted_text,
            sep="",
            file=self.output,
            end="",
        )

    def print_zero_to_counter(self):
        """Print a zero. Use this to initialize the counter."""
        self.print_counter(-1)  # print_counter adds one to its arg.

    def end_count(self, append_newline=True):
        """Place the cursor at the end of the line and show it."""
        end_arg = "\n" if append_newline else ""
        self.set_cursor_column_to(self.after_text)
        print(self.show_cursor, file=self.output, end=end_arg)


class Dupes(dict):
    """TODO: Write This"""

    def __init__(self, dictionary, paths_and_checksums):
        self,
        self.mapped = dictionary
        self.paths_and_checksums = paths_and_checksums

    def path_not_in_values(self, path_value):
        """Checks if a path exists within a dict's collection values."""
        for paths in self.mapped.values():
            if path_value in paths:
                return False
        return True

    def sort_values(self, sort_key=None):
        """Convert collections to lists and sort them in place."""
        for dict_key in self.mapped.keys():
            list_of_values = list(self.mapped[dict_key])
            list_of_values.sort(key=sort_key)
            self.mapped[dict_key] = list_of_values

    def status(self):
        """Create values to pass to search_for_dupes' return tuple.

        Returns:
            An unnamed tuple suitable which can be unpacked into the
            search_for_dupes_return_tuple constructor. See
            search_for_dupes' docstring for more info.
        """

        # Prepare to create description value.
        total_errors = self.paths_and_checksums.permission_errors
        total = self.sum_length_of_values()
        plural = total > 1
        duplicate_s_ = "duplicates" if plural else "duplicate"
        were_or_was = "were" if plural else "was"
        description_of_the_result = f"{total} {duplicate_s_} {were_or_was}"

        # Determine what values to return.
        if self.paths_and_checksums.permission_errors and not self.mapped:
            description = f"{total_errors} or more files couldn't be read."
            return_code = 1
        elif self.paths_and_checksums.permission_errors and self.mapped:
            description = (
                f"{description_of_the_result} found, however"
                f" {total_errors} or more files couldn't be read."
            )
            return_code = 1
        elif not self.mapped:
            description = "No duplicates were found."
            return_code = 0
        else:
            description = f"{description_of_the_result} found."
            return_code = 0

        return (self, description, return_code)

    def sum_length_of_values(self):
        """Sum the lengths of all a dict's values and return the sum"""
        sum_total_length = 0
        for dict_value in self.mapped.values():
            sum_total_length += len(dict_value)
        return sum_total_length

    def write_to_csv(
        self, file, labels, encoding="utf-8", errors="replace", mode="x", **kwargs
    ):
        """Writes out the contents of a dict as an Excel style CSV.

        Args:
            output_file: A path-like object or an integer file description.
            labels: A iterable of strings or numbers which are written
                once as the first row of the file. To omit the label row
                pass []. To print a blank row pass ['', ''].
            encoding: Passed to the open function. Defaults to 'utf-8'.
            errors: Passed to the open function. Defaults to 'replace'.
            mode: Passed to the open function. Defaults to 'x'.
            **kwargs: Passed to the open function.
        """

        with open(
            file, encoding=encoding, mode=mode, errors=errors, **kwargs
        ) as csv_file:
            writer = csv.writer(csv_file)
            if labels:
                writer.writerow(labels)

            for file_with_duplicate, duplicates_list in self.mapped.items():
                writer.writerow([file_with_duplicate, duplicates_list[0]])
                if len(duplicates_list) > 1:
                    for duplicate in duplicates_list[1:]:
                        writer.writerow(["", duplicate])


# Functions
def make_file_path_unique(path):
    """Makes a similarly named path object if a path already exists.

    Args:
        path: An instance of pathlib.Path or its subclasses.

    Raises:
        FileExistsError after 255 attempts to determine a unique path.

    Returns:
        The value of path, or another path object with a similar name.
    """

    new_path = None
    for numeric_suffix in range(1, 256):
        if not path.exists() and not new_path:
            return path
        elif not new_path or new_path.exists():
            new_path = path.with_stem(path.stem + str(numeric_suffix))
        else:
            return new_path
    raise FileExistsError("A unique path name could not be created.")


def checksum_paths(collection_of_paths):
    """Checksums files and stores their checksums alongside their paths.

    Args:
        collection_of_paths: A collection of strings, or instances of
            pathlib.Path and its subclasses.

    Returns:
        A named tuple (paths_and_sums, permission_errors), where
        paths_and_sums is a list of tuples which contain a file path
        and the checksum integer of the corresponding file, and
        permission_errors is an integer representing the number of
        permission errors suppressed.
    """

    result_tuple = collections.namedtuple(
        "checksum_paths_return_tuple", ["paths_and_sums", "permission_errors"]
    )
    permission_errors = 0
    paths_and_checksums = []
    for file_path in collection_of_paths:
        try:
            with open(file_path, mode="rb") as file:
                checksum = checksummer(file.read())
        except IsADirectoryError:
            continue  # Skip directories.
        except PermissionError:
            permission_errors += 1
            continue
        paths_and_checksums.append((file_path, checksum))
    return result_tuple(paths_and_checksums, permission_errors)


def checksum_paths_and_show_progress(collection_of_paths):
    """As checksum_paths but prints the loop's progress to terminal."""
    checksum_progress = ProgressCounter(
        collection_of_paths,
        text_before_counter="Reading file ",
        text_after_counter=" of {}.",
    )

    result_tuple = collections.namedtuple(
        "checksum_paths_return_tuple", ["paths_and_sums", "permission_errors"]
    )
    permission_errors = 0
    paths_and_checksums = []
    try:
        checksum_progress.print_text_for_counter()
        for index, file_path in enumerate(collection_of_paths):
            try:
                with open(file_path, mode="rb") as file:
                    checksum = checksummer(file.read())
            except IsADirectoryError:
                continue  # Skip directories.
            except PermissionError:
                permission_errors += 1
                continue
            paths_and_checksums.append((file_path, checksum))
            checksum_progress.print_counter(index)
    finally:
        checksum_progress.end_count()
    return result_tuple(paths_and_checksums, permission_errors)


def locate_dupes(paths_and_checksums):
    """Locates duplicate files by comparing their checksums.

    Args:
        paths_and_checksums: A list of tuples, each containing a file
            path and the checksum of the corresponding file.

    Returns:
        A dictionary of paths mapped to sets of paths whose associated
        checksums match the checksum associated with the path key.
        The dictionary never contains a path more than once.
    """

    dupes = collections.defaultdict(set)
    for index, element in enumerate(paths_and_checksums.paths_and_sums):
        path_being_searched, checksum_being_searched = element

        for current_path, current_checksum in paths_and_checksums.paths_and_sums[
            index + 1 :
        ]:
            checksums_are_equal = checksum_being_searched == current_checksum
            if checksums_are_equal and path_not_in_dict(path_being_searched, dupes):
                dupes[path_being_searched].add(current_path)
    return Dupes(dupes, paths_and_checksums)


def locate_dupes_and_show_progress(paths_and_checksums):
    """As locate_dupes but prints the loop's progress to terminal."""
    comparisons_progress = ProgressCounter(
        paths_and_checksums.paths_and_sums,
        text_before_counter="Comparing file ",
        text_after_counter=" of {}.",
    )

    dupes = collections.defaultdict(set)
    try:
        comparisons_progress.print_text_for_counter()
        for index, element in enumerate(paths_and_checksums.paths_and_sums):
            path_being_searched, checksum_being_searched = element
            comparisons_progress.print_counter(index)

            for (
                current_path,
                current_checksum,
            ) in paths_and_checksums.paths_and_sums[index + 1 :]:
                checksums_are_equal = checksum_being_searched == current_checksum
                if checksums_are_equal and path_not_in_dict(path_being_searched, dupes):
                    dupes[path_being_searched].add(current_path)
    finally:
        comparisons_progress.end_count()
    return Dupes(dupes, paths_and_checksums)


def path_not_in_dict(path_value, dictionary):
    """Checks if a path exists within a dict's collection values."""
    for paths in dictionary.values():
        if path_value in paths:
            return False
    return True


def search_stdin_and_stream_results(csv_labels):
    """Search paths from stdin for dupes and stream results to stdout.

    Args:
        csv_labels: A iterable of strings or numbers which are written
            once as the first row of the file. To omit the label row
            pass []. To print a blank row pass ['', ''].

    Returns:
        A list of return codes produced by the search_for_dupes calls.
    """

    return_codes = []
    for index, line in enumerate(sys.stdin):
        search_result = search_for_dupes(line.rstrip(), show_progress=args.progress)
        csv_labels_arg = [] if index > 0 else csv_labels
        # The fd is kept open so writes append.
        search_result.dupes.write_to_csv(
            sys.stdout.fileno(), csv_labels_arg, closefd=False
        )
        return_codes.append(search_result.return_code)
    return return_codes


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


def get_listdupes_args(overriding_args=None):
    """Parses arguments with the argparse module and returns the result.

    By default it parses the arguments passed to sys.argv.
    Optionally it can parse a different set of arguments,
    effectively overriding sys.argv. The returned object uses the
    arguments's long names as attributes, with each attribute holding
    the result of parsing that argument.
    E.g. args.progress contains the value of the --progress argument.

    Args:
        overriding_args: Accepts a list of strings to parse.
            This is passed to the parser's parse_args() method.
            When the value is None (As it is by default) parse_args()
            taking its arguments from sys.argv.

    Returns:
        An argparse.Namespace object with the app's arguments.
    """

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    # Replace the default -h with a reformatted help description.
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        help="Show this help message and exit.",
    )
    parser.add_argument(
        "starting_folder",
        nargs="?",
        help="Accepts a single path from the terminal.",
    )
    parser.add_argument(
        "-f",
        "--filter",
        action="store_true",
        help=(
            "Accept starting folder paths from stdin and output results to stdout."
            "  Note that this may not be what you want, as it will"
            " list duplicates contained within each starting folder,"
            " not across multiple starting folders."
        ),
    )
    parser.add_argument(
        "-p",
        "--progress",
        action="store_true",
        help="Print a progress counter to stderr. This may slow things down.",
    )
    args = parser.parse_args(args=overriding_args)
    return args


def search_for_dupes(starting_folder, show_progress=False):
    """Searches a path and its subfolders for duplicate files.

    Args:
        starting_folder: A string of the path to recursively search for
            duplicate files.
        show_progress: A bool indicating whether to display the progress
            of checksumming and comparison processes. Defaults to False.

    Returns:
        A named tuple (dupes, description, return_code), where dupes
        is a dictionary (As the return value of locate_dupes but with
        its sets replaced by lists), description is a string which
        describes the result, and return_code is an integer
        corresponding to the error.
    """

    result_tuple = collections.namedtuple(
        "search_for_dupes_return_tuple", ["dupes", "description", "return_code"]
    )

    # Return early if starting_folder is not provided.
    if starting_folder is None:
        return result_tuple({}, "No starting folder was provided.", 1)

    # Gather all files except those starting with "." and checksum them.
    # Then compare the checksums and make a dict of duplicate files.
    unexpanded_starting_folder = pathlib.Path(starting_folder)
    starting_folder = unexpanded_starting_folder.expanduser()
    if show_progress:
        print("Gathering files...", file=sys.stderr)
        glob_module_arg = str(starting_folder) + "/**/[!.]*"
        sub_paths = glob.glob(glob_module_arg, recursive=True)
        checksum_result = checksum_paths_and_show_progress(sub_paths)
        checksum_result.paths_and_sums.sort()
        dupes = locate_dupes_and_show_progress(checksum_result)
    else:
        sub_paths = starting_folder.glob("**/[!.]*")
        checksum_result = checksum_paths(sub_paths)
        checksum_result.paths_and_sums.sort()
        dupes = locate_dupes(checksum_result)

    # Sort the duplicates to prepare them for output.
    dupes.sort_values()

    return_values = dupes.status()
    return result_tuple(*return_values)


def main(args):
    """The functionality of the listdupes command-line app."""
    result_tuple = collections.namedtuple(
        "main_return_tuple", ["final_message", "return_code"]
    )

    # Determine the output's eventual file path.
    # NOTE: This is done as early as possible to allow for an early exit
    # if we can't write to a drive.
    output_file_name = "listdupes_output.csv"
    output_path = pathlib.Path("~", output_file_name).expanduser()
    try:
        output_path = make_file_path_unique(output_path)
    except FileExistsError:
        return result_tuple(
            "Your home folder has a lot of output files. Clean up to proceed.",
            1,
        )

    column_labels = ["File", "Duplicates"]

    if args.filter:
        if args.progress:
            print("Processing input stream...", file=sys.stderr)
        return_codes_from_search = search_stdin_and_stream_results(column_labels)
        return result_tuple("", 3 if any(return_codes_from_search) else 0)

    # Call search_for_dupes, print its description, and return early if
    # there aren't any dupes.
    search_result = search_for_dupes(args.starting_folder, show_progress=args.progress)
    print(search_result.description, file=sys.stderr)
    if not search_result.dupes:
        return result_tuple("", search_result.return_code)

    # Format the duplicate paths as a CSV and write it to a file.
    try:
        search_result.dupes.write_to_csv(output_path, column_labels)
    except Exception:
        # Print data to stdout if a file can't be written. If stdout
        # isn't writeable the shell will provide its own error message.
        handle_exception_at_write_time(sys.exc_info())
        search_result.dupes.write_to_csv(sys.stdout.fileno(), column_labels)
        return result_tuple("", 1)

    return result_tuple(
        f"The list of duplicates has been saved to {output_path.parent}.",
        search_result.return_code,
    )


# Run the app!
if __name__ == "__main__":
    args = get_listdupes_args()  # The parser can exit with 2.
    main_result = main(args)
    if main_result.final_message:
        print(main_result.final_message, file=sys.stderr)
    sys.exit(main_result.return_code)
