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
    "get_checksum_input_values",
    "locate_dupes",
    "locate_dupes_and_show_progress",
    "main",
    "search_for_dupes",
    "PreviousFileNotFoundError",
]
__version__ = "6.0.0-beta.4"
__author__ = "Chris Dobbins"
__license__ = "BSD-2-Clause"


# Modules
import argparse
import collections
import csv
import datetime
import json
import pathlib
import sys
from zlib import crc32 as checksummer


# Classes
class _Cursor:
    """The terminal's cursor."""

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
    """A counter displaying an iteration's progress on the terminal."""

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
        """Convert collections to sorted lists."""
        for dict_key in self.keys():
            self[dict_key] = sorted(self[dict_key], key=sort_key)

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
        os_errors = self.checksum_result.os_errors.values()
        errors = 0 if not os_errors else sum([len(x) for x in os_errors])
        total = self.sum_length_of_values()
        plural = total > 1
        duplicate_s_ = "duplicates" if plural else "duplicate"
        were_or_was = "were" if plural else "was"
        description_of_the_result = f"{total} {duplicate_s_} {were_or_was}"

        # Determine what values to return.
        if errors and not self:
            description = (
                "No duplicates were found, however"
                f" {errors} or more files couldn't be read."
            )
            return_code = 1
        elif errors and self:
            description = (
                f"{description_of_the_result} found, however"
                f" {errors} or more files couldn't be read."
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
        """Sum the lengths of an instance's values and return the sum."""
        sum_of_lengths = sum([len(mapped_value) for mapped_value in self.values()])
        return sum_of_lengths

    def write_any_items_to(self, file, format="csv", **kwargs):
        """Write the contents of the mapping to a file.

        Args:
            file: A path-like object or integer file descriptor.
            format: A string specifying the format to be written.
                Defaults to 'csv'.
            **kwargs: Passed to the writer function.
        """

        kwargs_for_writer = {}
        kwargs_for_writer.update(**kwargs)
        if not any(self.values()):
            return None
        writer = {"csv": self.write_to_csv, "json": self.write_to_json}
        writer[format](file, **kwargs_for_writer)

    def write_to_csv(self, file, labels=["File", "Duplicates"], **kwargs):
        """Write the contents of the mapping as an Excel-style CSV.

        The file opens in: mode='x', encoding='utf-8', errors='replace'.

        Args:
            file: A path-like object or integer file descriptor.
            labels: A iterable of strings or numbers which are written
                once as the first row of the file. To omit the label row
                pass []. To print a blank row pass ['', '']. The default
                is ['File', 'Duplicates']
            **kwargs: Passed to open().
        """

        kwargs_for_open = {"mode": "x", "encoding": "utf-8", "errors": "replace"}
        kwargs_for_open.update(**kwargs)  # Allows override of defaults.
        with open(file, **kwargs_for_open) as csv_file:
            writer = csv.writer(csv_file)
            if labels:
                writer.writerow(labels)

            for file_with_duplicate, duplicates_list in self.items():
                writer.writerow([file_with_duplicate, duplicates_list[0]])
                if len(duplicates_list) > 1:
                    for duplicate in duplicates_list[1:]:
                        writer.writerow(["", duplicate])

    def write_to_json(self, file, **kwargs):
        """Write the contents of the mapping as a JSON.

        The file opens in: mode='x', encoding='utf-8', errors='replace'.

        Args:
            file: A path-like object or integer file descriptor.
            **kwargs: Passed to open().
        """

        kwargs_for_open = {"mode": "x", "encoding": "utf-8", "errors": "replace"}
        kwargs_for_open.update(**kwargs)  # Allows override of defaults.
        json_safe_dict = {str(k): [str(path) for path in v] for k, v in self.items()}
        with open(file, **kwargs_for_open) as json_file:
            json.dump(json_safe_dict, json_file)


class PreviousFileNotFoundError(Exception):
    """A previously located file can't be found now."""

    def __init__(self, message, filename, filename2=None):
        """The values used to initialize a new instance of the error.

        Args:
            message: A description of the error.
            filename: The path of the file which raised the exception.
            filename2: The first parent path of 'filename' which is
                found to exist, if any. The default is None.
        """

        self.message = message
        self.filename = filename
        self.filename2 = filename2


# Functions
def _get_listdupes_args(overriding_args=None):
    """Parse arguments with the argparse module and return the result.

    Args:
        overriding_args: Accepts a list of strings to parse.
            This is passed to the parser's parse_args() method.
            When the value is None (As it is by default) parse_args()
            taking its arguments from sys.argv.

    Returns:
        An argparse.Namespace object containing the app's arguments.
        The object uses the arguments's long names as attributes,
        with each attribute holding the result of parsing that argument.
        E.g. args.progress holds the value of the --progress argument.
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
        "-a",
        "--archive_folder",
        action="store_true",
        help="Write the paths found in the starting folder to a file and quit.",
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
        "-j",
        "--json",
        action="store_true",
        help="Write the output as a JSON file instead of a CSV.",
    )
    parser.add_argument(
        "-p",
        "--progress",
        action="store_true",
        help="Print a progress counter to stderr. This may slow things down.",
    )
    parser.add_argument(
        "-r",
        "--read_archive",
        action="store_true",
        help="Read paths from an archive file instead of from a starting folder.",
    )
    args = parser.parse_args(args=overriding_args)
    return args


def _make_file_path_unique(path):
    """Make a similarly named path object if a path already exists.

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


def _make_unique_paths(paths_to_make, destination=("~", "home folder")):
    """Make unique paths and raise a helpful error if one can't be made.

    Args:
        paths_to_make: A list of tuples (str, str), each containing
            the name of a file and a description of its purpose
            to use in the creation of errors.
        destination: A tuple (str, str) containing the root path of the
            paths to be created and a description to use in errors.
            Defaults to the user's home folder.

    Raises:
        FileExistsError after 255 attempts to determine a unique path.

    Returns:
        A named tuple of unique paths. Its fields are named after each
        path's description (E.g. 'log file' is accessed via .log_file).
    """

    names_for_tuple = []
    root_path, location = destination
    unique_paths = []
    for file_name, description in paths_to_make:
        description_as_field_name = "_".join(description.split())
        names_for_tuple.append(description_as_field_name)
        path = pathlib.Path(root_path, file_name).expanduser()
        try:
            unique_path = _make_file_path_unique(path)
        except FileExistsError:
            message = (
                f"Your {location} has a lot of {description}s. Clean up to proceed."
            )
            raise FileExistsError(message)
        unique_paths.append(unique_path)

    result_tuple = collections.namedtuple(
        "make_unique_paths_return_tuple", names_for_tuple
    )
    return result_tuple(*unique_paths)


def _starting_path_is_invalid(path, read_archive=False):
    """Determine if the path is an existing folder.

    Args:
        path: An instance of pathlib.Path or its subclasses.
        read_archive: A bool. Defaults to False.

    Returns:
        A string describing why the path is invalid, or an empty string.
    """

    if read_archive and not path:
        return "An archive file is required."
    elif read_archive and not path.exists():
        return "No such file exist at that location."
    elif read_archive and path.is_dir():
        return "The starting path must be a file."
    elif not path:
        return "A starting folder is required."
    elif not path.exists():
        return "No such folder exist at that location."
    elif not read_archive and not path.is_dir():
        return "The starting path must be a folder."
    else:
        return ""


def _find_sub_paths(starting_folder, return_set=False, show_work_message=False):
    """Search sub-folders and return paths not starting with a dot."""
    if show_work_message:
        print("Gathering files...", file=sys.stderr)
    sub_paths = starting_folder.glob("**/[!.]*")
    if not return_set:
        return sub_paths
    else:
        return set(sub_paths)


def _read_archive_from(file, **kwargs):
    """Read, verify, and return the starting folder archive."""
    kwargs_for_open = {"mode": "r", "encoding": "utf-8", "errors": "replace"}
    kwargs_for_open.update(**kwargs)  # Allows override of defaults.
    with open(file, **kwargs_for_open) as archive_file:
        archived = json.load(archive_file)
    archived["creation_time"] = datetime.datetime.fromtimestamp(
        archived["creation_time"], tz=datetime.timezone.utc
    )
    archived["starting_path"] = pathlib.Path(archived["starting_path"])
    archived["sub_paths"] = [
        pathlib.Path(str_path) for str_path in archived["sub_paths"]
    ]
    return archived


def _get_creation_time_from_cache(file_path):
    """Return a cache's archive creation time with only a short read."""
    with open(file_path) as file:
        first_kilobyte_of_file = file.read(1024)
    possible_float = None
    start_of_file, comma, _ = first_kilobyte_of_file.partition(",")
    if comma:
        _, key_value_seperator, substring_before_comma = start_of_file.rpartition(": ")
        if key_value_seperator:
            possible_float = substring_before_comma
    try:
        possible_timestamp = float(possible_float)
        creation_time = datetime.datetime.fromtimestamp(
            possible_timestamp, tz=datetime.timezone.utc
        )
    except (ValueError, TypeError, OSError, OverflowError):
        return None
    return creation_time


def _write_archive_to(file_path, sub_paths, starting_folder, **kwargs):
    """Dump the subpaths to an archive file."""
    kwargs_for_open = {"mode": "x", "encoding": "utf-8", "errors": "replace"}
    kwargs_for_open.update(**kwargs)  # Allows override of defaults.
    json_safe_subpaths = [str(path) for path in sub_paths]
    current_time = datetime.datetime.now(datetime.timezone.utc).timestamp()
    json_safe_starting_folder = str(starting_folder)
    archive = {
        "creation_time": current_time,
        "starting_path": json_safe_starting_folder,
        "sub_paths": json_safe_subpaths,
    }
    with open(file_path, **kwargs_for_open) as json_file:
        json.dump(archive, json_file)


def _do_pre_checksumming_tasks(
    *,
    paths_to_make,
    main_return_constructor,
    starting_path,
    starting_path_required,
    read_archive,
    write_archive,
    hardcoded_cache_path,
    show_progress,
):
    """Give main() the means to either proceed or exit early.

    Since this is a fairly abstract function with many arguments it uses
    required keyword-only arguments to help prevent errors in usage.

    Args:
        paths_to_make: A list of tuples, passed to _make_unique_paths().
        main_return_constructor: Main()'s return value constructor.
        starting_folder: An instance of pathlib.Path or its subclasses.
        starting_path_required: A bool.
        read_archive: A bool.
        show_progress: A bool.

    Return:
        A named tuple ("unique_path", "archive", "early_exit") where
        'unique_path' is the returned value of _make_unique_paths() and
        'archive' is either an empty dict or one holding the contents
        of an archived file, and 'early_exit' is a valid return value
        for main().
    """

    result_tuple = collections.namedtuple(
        "do_pre_checksumming_tasks_return_tuple",
        ["unique_path", "archive", "early_exit"],
    )
    # Determine the eventual paths of all necessary files.
    try:
        unique_path = _make_unique_paths(paths_to_make)
    except FileExistsError as e:
        return result_tuple(None, {}, main_return_constructor(str(e), 1))

    # Exit early if a starting path is required and the path is invalid.
    issue_with_starting_path = _starting_path_is_invalid(
        starting_path, read_archive=read_archive
    )
    if issue_with_starting_path and starting_path_required:
        return result_tuple(
            None, {}, main_return_constructor(issue_with_starting_path, 1)
        )

    # Exit early if the archive isn't a valid file
    # or doesn't match the existing cache.
    if read_archive:
        archive = {}
        try:
            archive = _read_archive_from(starting_path)
        except (json.JSONDecodeError, ValueError, KeyError):
            message = "The file you have chosen is not a valid archive."
            return result_tuple(
                unique_path, archive, main_return_constructor(message, 1)
            )

        if hardcoded_cache_path.exists():
            creation_time_from_cache = _get_creation_time_from_cache(
                hardcoded_cache_path
            )
            # Using the archive's creation time as a quasi-unique ID
            # check that the archive and cache match.
            if not creation_time_from_cache == archive["creation_time"]:
                message = (
                    "The cache file is holding work which was done on another"
                    " archive.\n"
                    "Please save that work by moving the cache file to a seperate"
                    " location\n"
                    "or simply delete the cache if you no longer need it."
                )
                return result_tuple(
                    unique_path, archive, main_return_constructor(message, 1)
                )
        return result_tuple(unique_path, archive, None)

    # Archive subpaths to a file and exit if -a has been passed.
    if write_archive:
        sub_paths = _find_sub_paths(starting_path, show_work_message=show_progress)
        sorted_sub_paths = sorted(sub_paths)
        _write_archive_to(unique_path.folder_archive, sorted_sub_paths, starting_path)
        message = "The folder has been archived."
        return result_tuple(None, {}, main_return_constructor(message, 0))

    return result_tuple(unique_path, {}, None)


def _describe_old_archive(archive_creation_time):
    """If an archive is old return a description of how old it is."""
    current_time = datetime.datetime.now(datetime.timezone.utc)
    time_between_creation_and_now = current_time - archive_creation_time
    a_year = datetime.timedelta(weeks=52)
    half_a_year = datetime.timedelta(days=183)
    roughly_a_month = datetime.timedelta(days=31)
    a_week = datetime.timedelta(days=7)

    if time_between_creation_and_now > a_year:
        description = "a year"
    elif time_between_creation_and_now > half_a_year:
        description = "half a year"
    elif time_between_creation_and_now > roughly_a_month:
        description = "a month"
    elif time_between_creation_and_now > a_week:
        description = "a week"
    else:
        description = ""

    if description:
        return f"This archive was made over {description} ago."
    else:
        return ""


def _read_cache_from(file, **kwargs):
    """Read and return the cached state of a checksum_files function."""
    kwargs_for_open = {"mode": "r", "encoding": "utf-8", "errors": "replace"}
    kwargs_for_open.update(**kwargs)  # Allows override of defaults.
    with open(file, **kwargs_for_open) as cache_file:
        cached = json.load(cache_file)
    cached["archive_creation_time"] = datetime.datetime.fromtimestamp(
        cached["archive_creation_time"], tz=datetime.timezone.utc
    )
    cached["starting_path_from_archive"] = pathlib.Path(
        cached["starting_path_from_archive"]
    )
    for key, value in cached["os_errors"].items():
        cached["os_errors"][key] = [(x, y) for x, y in value]
    cached["paths_and_sums"] = [
        (pathlib.Path(x), y) for x, y in cached["paths_and_sums"]
    ]
    return cached


def get_checksum_input_values(
    starting_path,
    show_progress,
    archived_data={},
    cache_path=None,
):
    """Return the initial values to pass to a checksum function.

    Args:
        starting_path: An instance of pathlib.Path or its subclasses.
        show_progress: A bool indicating whether the path gathering
            function should print a message when it starts.
        archived_data: Either an empty dict or one holding the contents
            of an archive file. Defaults to empty.
        cache_path: Either None or an instance of pathlib.Path
            (or its subclasses) representing where to check for a cache.
            Defaults to None.

    Returns:
        A named tuple ('paths', 'paths_and_sums', 'os_errors', 'place',
        'created', 'starting_folder').

        'paths' is a list of pathlib.Path objects.

        'paths_and_sums' is a list which is either empty or contains
        tuples of (Path object, Int) which pair a Path object and
        the checksum of the associated file.

        'os_errors' is a dictionary with keys for suppressed os errors
        which are mapped to sets which may be empty, or may contain
        tuples of (Str, Str) pairing a string representation of
        a path with a string describing the error that file raised.

        'place' is an integer representing the index of the last file
        in an archive to be checksummed and cached. If no cache exists
        it defaults to 0.

        'cache_details' is either None or a named tuple
        ('path', 'archive_creation_time', 'starting_path_from_archive')
        where 'path' is an instance of pathlib.Path (or its subclasses),
        'archive_creation_time' is a datetime object, and
        'starting_path_from_archive' is either an instance of
        pathlib.Path (or its subclasses).
    """

    result_tuple = collections.namedtuple(
        "get_checksum_input_values_return_tuple",
        ["paths", "paths_and_sums", "os_errors", "place", "cache_details"],
    )
    cache_details_tuple = collections.namedtuple(
        "cache_details", ["path", "archive_creation_time", "starting_path_from_archive"]
    )
    os_errors = {
        "permission_errors": set(),
        "file_not_found_errors": set(),
        "misc_errors": set(),
    }
    escape_codes = ("\x1b[1m", "\x1b[0m") if sys.stderr.isatty() else ("", "")
    bold, reset_style = escape_codes

    if archived_data and cache_path and cache_path.exists():
        old_archive_description = _describe_old_archive(archived_data["creation_time"])
        if old_archive_description:
            print(bold, old_archive_description, reset_style, sep="", file=sys.stderr)
        cached = _read_cache_from(cache_path)
        place_in_sub_paths = cached["place"]
        paths = archived_data["sub_paths"][place_in_sub_paths:]
        cache_details = cache_details_tuple(
            cache_path,
            cached["archive_creation_time"],
            cached["starting_path_from_archive"],
        )
        return result_tuple(
            paths,
            cached["paths_and_sums"],
            cached["os_errors"],
            cached["place"],
            cache_details,
        )
    elif archived_data and cache_path:
        old_archive_description = _describe_old_archive(archived_data["creation_time"])
        if old_archive_description:
            print(bold, old_archive_description, reset_style, sep="", file=sys.stderr)
        cache_details = cache_details_tuple(
            cache_path,
            archived_data["creation_time"],
            archived_data["starting_path"],
        )
        return result_tuple(
            archived_data["sub_paths"],
            [],
            os_errors,
            0,
            cache_details,
        )
    else:
        paths = _find_sub_paths(
            starting_path, show_work_message=show_progress, return_set=show_progress
        )
        cache_details = None
        return result_tuple(
            paths,
            [],
            os_errors,
            0,
            cache_details,
        )


def _chunk_file(file_object_to_chunk, chunk_size=524288):
    """Yield from the file a chunk of the specified size."""
    while True:
        chunk = file_object_to_chunk.read(chunk_size)
        if not chunk:
            break
        yield chunk


def _check_path_for_disconnection(file_path):
    """Check if any of a path's parent path segments can't be found.

    Args:
        file_path: An instance of pathlib.Path or its subclasses.
    Raises:
        PreviousFileNotFoundError
    """

    missing_parent_path = None
    longest_existing_parent = None
    for parent_path in file_path.parents:
        if not parent_path.exists() and missing_parent_path is None:
            missing_parent_path = parent_path
        elif parent_path.exists() and missing_parent_path:
            longest_existing_parent = parent_path
    if missing_parent_path:
        message = "A previously located file couldn't be located."
        if longest_existing_parent:
            message += f" Nothing beyond {longest_existing_parent} could be found."
        raise PreviousFileNotFoundError(
            message, missing_parent_path, filename2=longest_existing_parent
        )


def _checksum_file_and_store_outcome(
    file_path, results_container, errors_container, generator=_chunk_file
):
    """Checksum a file, storing the result or error via side-effect.

    Args:
        file_path: An instance of pathlib.Path or its subclasses.
        results_container: A container which is either empty or which
            contains tuples of (path-like object, Int) which pair
            a path with the checksum of the associated file.
        errors_container: A dictionary with keys for suppressed
            os errors mapped to sets which may be empty, or may contain
            tuples of (Str, Str) pairing a string representation of
            a path with a string describing the error that file raised.
        generator: The generator function taking one positonal arg
            which is used to split the file. The default is _chunk_file.
    """

    try:
        with open(file_path, mode="rb") as file:
            chunk_generator = generator(file)
            try:
                first_chunk = chunk_generator.__next__()
            except StopIteration:
                no_data = b""
                checksum = checksummer(no_data)
                results_container.append((file_path, checksum))
                return
            checksum = checksummer(first_chunk, 0)
            for chunk_of_bytes in chunk_generator:
                checksum = checksummer(chunk_of_bytes, checksum)
    except IsADirectoryError:
        return  # Don't count a directory as an error, just move on.
    except PermissionError as e:
        errors_container["permission_errors"].add((e.filename, e.strerror))
        return
    except FileNotFoundError as e:
        errors_container["file_not_found_errors"].add((e.filename, e.strerror))
        _check_path_for_disconnection(file_path)
        return
    except OSError as e:
        errors_container["misc_errors"].add((e.filename, e.strerror))
        return
    results_container.append((file_path, checksum))


def _write_cache_to(
    cache_details,
    paths_and_sums,
    os_errors,
    place,
    **kwargs,
):
    """Write the state of checksum_files function to a file.

    Args:
        cache_details: A named tuple ('path', 'archive_creation_time',
            'starting_path_from_archive') where 'file' is
            an instance of pathlib.Path or its subclasses,
            'archive_creation_time' is a datetime object and
            'starting_path_from_archive' is an instance of pathlib.Path
            or its subclasses. Any of the values can be None.
        paths_and_sums: A tuple (path-like object, Int).
        os_errors: A dictionary with info on suppressed os errors
        place: An integer representing the last completed checksum.
        **kwargs: Passed to the open function.
    """

    kwargs_for_open = {"mode": "w", "encoding": "utf-8", "errors": "replace"}
    kwargs_for_open.update(**kwargs)  # Allows override of defaults.
    if not paths_and_sums:  # If there are no checksums return early.
        return None
    json_safe_archive_creation_time = cache_details.archive_creation_time.timestamp()
    json_safe_paths_and_sums = [
        (str(path), checksum) for path, checksum in paths_and_sums
    ]
    json_safe_os_errors = {k: list(v) for k, v in os_errors.items()}
    json_safe_starting_path_from_archive = str(cache_details.starting_path_from_archive)
    cache = {
        "archive_creation_time": json_safe_archive_creation_time,
        "starting_path_from_archive": json_safe_starting_path_from_archive,
        "place": place,
        "os_errors": json_safe_os_errors,
        "paths_and_sums": json_safe_paths_and_sums,
    }
    with open(cache_details.path, **kwargs_for_open) as cache_file:
        json.dump(cache, cache_file)


def checksum_files(
    paths,
    results_state,
    errors_state,
    place_state=0,
    cache_details=None,
    sort_key=None,
):
    """Checksum files and return their paths, checksums, and errors.

    Args:
        paths: A container of path-like objects.
        results_state: A container which is either empty or which
            contains tuples of (path-like object, Int) which pair
            a path with the checksum of the associated file.
        errors_state: A dictionary with keys for suppressed os errors
            which are mapped to sets which may be empty, or may contain
            tuples of (Str, Str) pairing a string representation of
            a path with a string describing the error that file raised.
        place_state: An integer representing the index of the last file
            in an archive to be checksummed and cached.
            If no cache exists it defaults to 0.
        cache_details: Either None or a named tuple ('path',
            'archive_creation_time', 'starting_path_from_archive') where
            'file' is an instance of pathlib.Path or its subclasses,
            'archive_creation_time' is a datetime object and
            'starting_path_from_archive' is an instance of pathlib.Path
            or its subclasses. The default value of the kwarg is None.
        sort_key: A function for sorting the returned collections.
            The default of None dictates an ascending sort.

    Returns:
        A named tuple (paths_and_sums, os_errors), where
        paths_and_sums is a list of tuples which contain a path-like
        object and the checksum integer of the associated file,
        and os_errors is a dictionary with info on suppressed os errors.
    """

    result_tuple = collections.namedtuple(
        "checksum_files_return_tuple", ["paths_and_sums", "os_errors"]
    )
    paths_and_sums = results_state
    os_errors = errors_state
    place = 0  # Any prior place count is added during finalizing.
    try:
        for index, file_path in enumerate(paths):
            place = index
            _checksum_file_and_store_outcome(file_path, paths_and_sums, os_errors)
    finally:
        if cache_details:
            total_place = place_state + place
            _write_cache_to(cache_details, paths_and_sums, os_errors, total_place)
    paths_and_sums.sort(key=sort_key)
    os_errors = {k: sorted(v, key=sort_key) for k, v in os_errors.items()}
    return result_tuple(paths_and_sums, os_errors)


def checksum_files_and_show_progress(
    paths,
    results_state,
    errors_state,
    place_state=0,
    cache_details=None,
    sort_key=None,
):
    """As checksum_files but print the loop's progress to terminal."""
    checksum_progress = _ProgressCounter(
        paths,
        text_before_counter="Reading file ",
        text_after_counter=" of {}.",
    )

    result_tuple = collections.namedtuple(
        "checksum_files_return_tuple", ["paths_and_sums", "os_errors"]
    )
    paths_and_sums = results_state
    os_errors = errors_state
    place = 0  # Any prior place count is added during finalizing.
    try:
        checksum_progress.print_text_for_counter()
        for index, file_path in enumerate(paths):
            place = index
            _checksum_file_and_store_outcome(file_path, paths_and_sums, os_errors)
            checksum_progress.print_counter(index)
    finally:
        if cache_details:
            total_place = place_state + place
            _write_cache_to(cache_details, paths_and_sums, os_errors, total_place)
        checksum_progress.end_count()
    paths_and_sums.sort(key=sort_key)
    os_errors = {k: sorted(v, key=sort_key) for k, v in os_errors.items()}
    return result_tuple(paths_and_sums, os_errors)


def locate_dupes(checksum_result, sort_key=None):
    """Locate duplicate files by comparing their checksums.

    Args:
        checksum_result: A named tuple as per the result of one of the
            two checksum function.
        sort_key: A function for sorting the return value's
            collections. The default of None dictates an ascending sort.

    Returns:
        A Dupes object containing path keys which are mapped to lists of
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
    dupes.sort_values(sort_key=sort_key)
    return dupes


def locate_dupes_and_show_progress(checksum_result, sort_key=None):
    """As locate_dupes but print the loop's progress to terminal."""
    comparisons_progress = _ProgressCounter(
        checksum_result.paths_and_sums,
        text_before_counter="Comparing file ",
        text_after_counter=" of {}.",
    )

    dupes = Dupes({}, checksum_result)
    try:
        comparisons_progress.print_text_for_counter()
        for index, element in enumerate(checksum_result.paths_and_sums):
            path_being_searched, checksum_being_searched = element
            comparisons_progress.print_counter(index)

            for path, checksum in checksum_result.paths_and_sums[index + 1 :]:
                checksums_are_equal = checksum_being_searched == checksum
                if checksums_are_equal and dupes.not_in_values(path_being_searched):
                    dupes[path_being_searched].add(path)
    finally:
        comparisons_progress.end_count()
    dupes.sort_values(sort_key=sort_key)
    return dupes


def search_for_dupes(checksum_input, show_progress=False):
    """Search a collection of paths for duplicate files.

    Args:
        checksum_input: A named tuple as per the return value of
            get_checksum_input_values().
        show_progress: A bool indicating whether to display the progress
            of checksumming and comparison processes. Defaults to False.
    Returns:
        A named tuple (dupes, description, return_code), where dupes is
        a Dupes object (As per the return value of locate_dupes), and
        description and return_code are a string and an integer as per
        the return of Dupes.status().
    """

    result_tuple = collections.namedtuple(
        "search_for_dupes_return_tuple", ["dupes", "description", "return_code"]
    )
    # Checksum the paths, compare the checksums, then make a mapping
    # of paths to duplicate files and construct a Dupes object with it.
    if show_progress:
        checksum_result = checksum_files_and_show_progress(
            checksum_input.paths,
            checksum_input.paths_and_sums,
            checksum_input.os_errors,
            place_state=checksum_input.place,
            cache_details=checksum_input.cache_details,
        )
        dupes = locate_dupes_and_show_progress(checksum_result)
    else:
        checksum_result = checksum_files(
            checksum_input.paths,
            checksum_input.paths_and_sums,
            checksum_input.os_errors,
            place_state=checksum_input.place,
            cache_details=checksum_input.cache_details,
        )
        dupes = locate_dupes(checksum_result)

    search_status = dupes.status()
    return result_tuple(dupes, search_status.description, search_status.return_code)


def _write_any_errors_to(file_path, error_mapping, **kwargs):
    """If a mapping of errors has any values log them in a text file."""
    kwargs_for_open = {"mode": "x", "encoding": "utf-8", "errors": "replace"}
    kwargs_for_open.update(**kwargs)
    if not any(error_mapping.values()):
        return None
    with open(file_path, **kwargs_for_open) as file:
        for value in error_mapping.values():
            for path, error in value:
                file.write(f"'{path}' raised '{error}' and was not read.\n")
    return None


def _search_stdin_and_stream_results(
    unread_files_log_path,
    show_progress=False,
    format="csv",
):
    """Search paths from stdin for dupes and stream results to stdout.

    Args:
        unread_files_log_path: A path-like object giving the location
            to log suppressed read-errors to.
        show_progress: A bool indicating whether to display the progress
            of checksumming and comparison processes. Defaults to False.
        format: A string specifying the format to be written.
            Passed to Dupes.write_any_items_to(). Defaults to 'csv'.

    Returns:
        A list of return codes produced by the search_for_dupes calls.
    """

    kwargs_for_writer = {"format": format, "closefd": False}
    if show_progress:
        print("Processing input stream...", file=sys.stderr)
    return_codes = []
    for index, line in enumerate(sys.stdin):
        path = pathlib.Path(line.rstrip()).expanduser()
        problem_with_starting_path = _starting_path_is_invalid(path)
        if problem_with_starting_path:
            return_codes.append(1)
            continue
        checksum_input_values = get_checksum_input_values(path, show_progress)
        search_result = search_for_dupes(
            checksum_input_values, show_progress=show_progress
        )
        # Make the CSV's label row only print once.
        if index == 1 and format == "csv":
            kwargs_for_writer["labels"] = []
        # The fd is kept open so writes append.
        search_result.dupes.write_any_items_to(sys.stdout.fileno(), **kwargs_for_writer)
        os_errors = search_result.dupes.checksum_result.os_errors
        _write_any_errors_to(unread_files_log_path, os_errors, mode="a")
        return_codes.append(search_result.return_code)
    return return_codes


def _handle_exception_at_write_time(exception_info, file_ext):
    """Print a message and the exception's traceback without exiting."""
    error_message = (
        "An error prevented the app from saving its results.\n"
        "To recover the results copy the text below into an empty\n"
        f"text file and give it a name that ends with .{file_ext}"
    )
    escape_codes = ("\x1b[35m", "\x1b[0m") if sys.stderr.isatty() else ("", "")
    style_magenta, reset_style = escape_codes
    sys.excepthook(*exception_info)  # Prints traceback to stderr.
    print(style_magenta, error_message, reset_style, sep="", file=sys.stderr)


def main(overriding_args=None):
    """The functionality of the listdupes command-line app.

    Args:
        overriding_args: A list of strings to be passed to
            _get_listdupes_args() and parsed as arguments. When the
            value is None (As it is by default) that function parses
            the arguments from sys.argv.

    Returns:
        A named tuple (final_message, return_code), where final_message
        is a string describing either the number of dupes and errors or
        the reason for exiting early, and return_code is an integer.

        Code 0 indicates full success. Code 1 indicates either
        an early exit on an error, or a partial check for dupes
        in which read errors occurred. Code 3 indicates that
        one or more starting folders processed with the --filter flag
        did not fully succeed.
    """

    # Initial set-up.
    result_tuple = collections.namedtuple(
        "main_return_tuple", ["final_message", "return_code"]
    )
    args = _get_listdupes_args(overriding_args)  # This can exit with 2.
    if args.json:
        output_ext = format_arg = "json"
    else:
        output_ext = format_arg = "csv"
    traditional_unix_stdin_arg = pathlib.Path("-")
    filter_mode = args.filter or args.starting_folder == traditional_unix_stdin_arg
    starting_path_required = not filter_mode
    hardcoded_cache_path = pathlib.Path("~", "listdupes_cache").expanduser()
    paths_to_make = [
        (f"listdupes_output.{output_ext}", "output file"),
        ("listdupes_unread_files_log.txt", "unread files log"),
        ("listdupes_folder_archive.json", "folder archive"),
    ]

    # Do tasks like path validation and running the archive flag,
    # as they need the ability to exit very early.
    unique_path, archive, early_exit = _do_pre_checksumming_tasks(
        paths_to_make=paths_to_make,
        main_return_constructor=result_tuple,
        starting_path=args.starting_folder,
        starting_path_required=starting_path_required,
        read_archive=args.read_archive,
        write_archive=args.archive_folder,
        hardcoded_cache_path=hardcoded_cache_path,
        show_progress=args.progress,
    )
    if early_exit:
        return early_exit

    # Run as a Unix-style filter if an appropriate arg has been passed.
    if filter_mode:
        return_codes_from_search = _search_stdin_and_stream_results(
            unique_path.unread_files_log, show_progress=args.progress, format=format_arg
        )
        return result_tuple("", 3 if any(return_codes_from_search) else 0)

    # Determine input values for the checksum function.
    checksum_input_values = get_checksum_input_values(
        args.starting_folder,
        args.progress,
        archived_data=archive,
        cache_path=hardcoded_cache_path,
    )

    # Search for dupes and describe the result to the user.
    search_result = search_for_dupes(checksum_input_values, show_progress=args.progress)
    os_errors = search_result.dupes.checksum_result.os_errors
    print(search_result.description, file=sys.stderr)

    # Write an unread files log if needed.
    try:
        _write_any_errors_to(unique_path.unread_files_log, os_errors)
    except Exception:
        print("A log of the unread files couldn't be written.", file=sys.stderr)

    # Format the duplicate paths as a CSV and write it to a file.
    try:
        search_result.dupes.write_any_items_to(
            unique_path.output_file, format=format_arg
        )
    except Exception:
        # Print data to stdout if a file can't be written. If stdout
        # isn't writeable the shell will provide its own error message.
        _handle_exception_at_write_time(sys.exc_info(), format_arg)
        search_result.dupes.write_any_items_to(sys.stdout.fileno(), format=format_arg)
        return result_tuple("", 1)

    # Delete the cache if it's been read and results have been output.
    if args.read_archive and hardcoded_cache_path.exists():
        hardcoded_cache_path.unlink()

    save_description = (
        f"The list of duplicates has been saved to {unique_path.output_file}."
    )
    message = "" if not search_result.dupes else save_description
    return result_tuple(message, search_result.return_code)


# Run the app!
if __name__ == "__main__":
    try:
        main_result = main()
    except KeyboardInterrupt:
        print("You have quit the program.", file=sys.stderr)
        sys.exit(130)
    if main_result.final_message:
        print(main_result.final_message, file=sys.stderr)
    sys.exit(main_result.return_code)
