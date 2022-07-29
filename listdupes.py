#!/usr/bin/env python3

"""Check a folder and its subfolders for duplicate files.

Checks all files except for folders and those starting with a period.
Writes its output to listdupes_output.csv in the user's home folder.
"""

# Module Attributes
__all__ = [
    "checksum_files",
    "checksum_files_and_show_progress",
    "Dupes",
    "get_listdupes_args",
    "locate_dupes",
    "locate_dupes_and_show_progress",
    "main",
    "search_for_dupes",
]
__version__ = "6.0.0-alpha.4"
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
class _Cursor:
    """Provides structure to subclasses which write to terminal."""

    hide_cursor = "\x1b[?25l"  # Terminal escape codes.
    show_cursor = "\x1b[?25h"

    def __init__(self, output=sys.stderr):
        self.output = output

    def hide_cursor_from_user(self):
        print(_Cursor.hide_cursor, file=self.output, end="")

    def set_cursor_column_to(self, column_number):
        set_cursor_column_esc_code = f"\x1b[{column_number}G"
        print(set_cursor_column_esc_code, file=self.output, end="")


class _ProgressCounter(_Cursor):
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


class Dupes(collections.defaultdict):
    """The results of a search for duplicate files."""

    def __init__(self, dictionary, checksum_result):
        """The values used to initialize a new instance of Dupes.

        Args:
            dictionary: A dict which initializes Dupes' superclass.
            checksum_result: A named tuple containing the results of a
                checksum process. As per the return of checksum_files.
        """

        super().__init__(set, dictionary)
        self.checksum_result = checksum_result

    def not_in_values(self, test_value):
        """Check if a value exists within the mapping's values."""
        for collection in self.values():
            if test_value in collection:
                return False
        return True

    def sort_values(self, sort_key=None):
        """Convert collections to lists and sort them in place."""
        for dict_key in self.keys():
            list_of_values = list(self[dict_key])
            list_of_values.sort(key=sort_key)
            self[dict_key] = list_of_values

    def status(self):
        """Describe the dupes and errors found and assign a return code.

        Returns:
            A named tuple (description, return_code), where description
            is a string describing the number of dupes and errors, and
            return_code is an integer corresponding to the description.
        """

        result_tuple = collections.namedtuple(
            "search_status_return_tuple", ["description", "return_code"]
        )

        # Prepare to create description value.
        total_errors = self.checksum_result.permission_errors
        total = self.sum_length_of_values()
        plural = total > 1
        duplicate_s_ = "duplicates" if plural else "duplicate"
        were_or_was = "were" if plural else "was"
        description_of_the_result = f"{total} {duplicate_s_} {were_or_was}"

        # Determine what values to return.
        if self.checksum_result.permission_errors and not self:
            description = f"{total_errors} or more files couldn't be read."
            return_code = 1
        elif self.checksum_result.permission_errors and self:
            description = (
                f"{description_of_the_result} found, however"
                f" {total_errors} or more files couldn't be read."
            )
            return_code = 1
        elif not self:
            description = "No duplicates were found."
            return_code = 0
        else:
            description = f"{description_of_the_result} found."
            return_code = 0

        return result_tuple(description, return_code)

    def sum_length_of_values(self):
        """Sum the lengths of all a dict's values and return the sum"""
        sum_total_length = 0
        for dict_value in self.values():
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

            for file_with_duplicate, duplicates_list in self.items():
                writer.writerow([file_with_duplicate, duplicates_list[0]])
                if len(duplicates_list) > 1:
                    for duplicate in duplicates_list[1:]:
                        writer.writerow(["", duplicate])


# Functions
def _starting_path_is_invalid(path):
    """Determine if the path is an existing folder.

    Args:
        path: An instance of pathlib.Path or its subclasses.

    Returns:
        A string describing why the path is invalid, or an empty string.
    """

    if not path.exists():
        return "No such file exist at that location."
    elif not path.is_dir():
        return "The starting path must be a folder."
    else:
        return ""


def _make_file_path_unique(path):
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
            new_path = path.parent / (path.stem + str(numeric_suffix) + path.suffix)
        else:
            return new_path
    raise FileExistsError("A unique path name could not be created.")


def checksum_files(collection_of_paths):
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
        "checksum_files_return_tuple", ["paths_and_sums", "permission_errors"]
    )
    permission_errors = 0
    paths_and_sums = []
    for file_path in collection_of_paths:
        try:
            with open(file_path, mode="rb") as file:
                checksum = checksummer(file.read())
        except IsADirectoryError:
            continue  # Skip directories.
        except PermissionError:
            permission_errors += 1
            continue
        paths_and_sums.append((file_path, checksum))
    return result_tuple(paths_and_sums, permission_errors)


def checksum_files_and_show_progress(collection_of_paths, debug=False):
    """As checksum_files but prints the loop's progress to terminal."""
    checksum_progress = _ProgressCounter(
        collection_of_paths,
        text_before_counter="Reading file ",
        text_after_counter=" of {}.",
    )

    # Debugging setup.
    output_file_name = "listdupes_debug_log.txt"
    output_path = pathlib.Path("~", output_file_name).expanduser()
    debug_message = "Last file read was # {}, located at {}\n"

    result_tuple = collections.namedtuple(
        "checksum_files_return_tuple", ["paths_and_sums", "permission_errors"]
    )
    permission_errors = 0
    paths_and_sums = []
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
            paths_and_sums.append((file_path, checksum))
            checksum_progress.print_counter(index)
            if debug:
                with open(output_path, mode="w") as file:
                    file.write(debug_message.format(index, file_path))
    finally:
        checksum_progress.end_count()
    return result_tuple(paths_and_sums, permission_errors)


def locate_dupes(checksum_result):
    """Locates duplicate files by comparing their checksums.

    Args:
        checksum_result: A list of tuples, each containing a file
            path and the checksum of the associated file.

    Returns:
        A Dupes object containing path keys which are mapped to sets of
        paths whose associated checksums match the checksum associated
        with their path keys. Never contains a path more than once.
    """

    dupes = Dupes({}, checksum_result)
    for index, element in enumerate(checksum_result.paths_and_sums):
        path_being_searched, checksum_being_searched = element

        for path, checksum in checksum_result.paths_and_sums[index + 1 :]:
            checksums_are_equal = checksum_being_searched == checksum
            if checksums_are_equal and dupes.not_in_values(path_being_searched):
                dupes[path_being_searched].add(path)
    return dupes


def locate_dupes_and_show_progress(checksum_result, debug=False):
    """As locate_dupes but prints the loop's progress to terminal."""
    comparisons_progress = _ProgressCounter(
        checksum_result.paths_and_sums,
        text_before_counter="Comparing file ",
        text_after_counter=" of {}.",
    )

    # Debugging setup.
    output_file_name = "listdupes_debug_log.txt"
    output_path = pathlib.Path("~", output_file_name).expanduser()
    debug_message = "Last file compared was # {}, located at {}\n"

    dupes = Dupes({}, checksum_result)
    try:
        comparisons_progress.print_text_for_counter()
        for index, element in enumerate(checksum_result.paths_and_sums):
            path_being_searched, checksum_being_searched = element
            comparisons_progress.print_counter(index)
            if debug:
                with open(output_path, mode="w") as file:
                    file.write(debug_message.format(index, path_being_searched))

            for path, checksum in checksum_result.paths_and_sums[index + 1 :]:
                checksums_are_equal = checksum_being_searched == checksum
                if checksums_are_equal and dupes.not_in_values(path_being_searched):
                    dupes[path_being_searched].add(path)
    finally:
        comparisons_progress.end_count()
    return dupes


def _search_stdin_and_stream_results(csv_labels):
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


def _handle_exception_at_write_time(exception_info):
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
        type=pathlib.Path,
        nargs="?",
        help="Accepts a single path from the terminal.",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Output a debug log.",
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


def search_for_dupes(starting_folder, show_progress=False, log_debugging=False):
    """Searches a path and its subfolders for duplicate files.

    Args:
        starting_folder: A string of the path to recursively search for
            duplicate files.
        show_progress: A bool indicating whether to display the progress
            of checksumming and comparison processes. Defaults to False.

    Returns:
        A named tuple (dupes, description, return_code), where dupes is
        a Dupes object (As per the return value of locate_dupes but with
        its sets sorted into lists), and description and return_code are
        a string and an integer as per the return of Dupes.status().
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
        checksum_result = checksum_files_and_show_progress(
            sub_paths, debug=log_debugging
        )
        checksum_result.paths_and_sums.sort()
        dupes = locate_dupes_and_show_progress(checksum_result, debug=log_debugging)
    else:
        sub_paths = starting_folder.glob("**/[!.]*")
        checksum_result = checksum_files(sub_paths)
        checksum_result.paths_and_sums.sort()
        dupes = locate_dupes(checksum_result)

    # Sort the duplicates to prepare them for output.
    dupes.sort_values()

    search_status = dupes.status()
    return result_tuple(dupes, search_status.description, search_status.return_code)


def main(args):
    """The functionality of the listdupes command-line app."""
    result_tuple = collections.namedtuple(
        "main_return_tuple", ["final_message", "return_code"]
    )

    # Determine the output's eventual file path.
    # NOTE: This is done as early as possible to allow for
    # an early exit if we can't write to a drive.
    output_file_name = "listdupes_output.csv"
    output_path = pathlib.Path("~", output_file_name).expanduser()
    try:
        output_path = _make_file_path_unique(output_path)
    except FileExistsError:
        message = "Your home folder has a lot of output files. Clean up to proceed."
        return result_tuple(message, 1)

    # Exit early if the path to the starting folder's invalid.
    problem_with_starting_path = _starting_path_is_invalid(args.starting_folder)
    if problem_with_starting_path:
        return result_tuple(problem_with_starting_path, 1)

    csv_column_labels = ["File", "Duplicates"]

    if args.filter:
        if args.progress:
            print("Processing input stream...", file=sys.stderr)
        return_codes_from_search = _search_stdin_and_stream_results(csv_column_labels)
        return result_tuple("", 3 if any(return_codes_from_search) else 0)

    # Call search_for_dupes, print its description, and return early if
    # there aren't any dupes.
    search_result = search_for_dupes(
        args.starting_folder, show_progress=args.progress, log_debugging=args.debug
    )
    print(search_result.description, file=sys.stderr)
    if not search_result.dupes:
        return result_tuple("", search_result.return_code)

    # Format the duplicate paths as a CSV and write it to a file.
    try:
        search_result.dupes.write_to_csv(output_path, csv_column_labels)
    except Exception:
        # Print data to stdout if a file can't be written. If stdout
        # isn't writeable the shell will provide its own error message.
        _handle_exception_at_write_time(sys.exc_info())
        search_result.dupes.write_to_csv(sys.stdout.fileno(), csv_column_labels)
        return result_tuple("", 1)

    message = f"The list of duplicates has been saved to {output_path.parent}."
    return result_tuple(message, search_result.return_code)


# Run the app!
if __name__ == "__main__":
    args = get_listdupes_args()  # The parser can exit with 2.
    main_result = main(args)
    if main_result.final_message:
        print(main_result.final_message, file=sys.stderr)
    sys.exit(main_result.return_code)
