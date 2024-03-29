#!/usr/bin/env python3

"""Check a folder and its subfolders for duplicate files.

Checks all files except for folders and those starting with a period.
Writes the results to listdupes_output.csv in the user's home folder.
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
__version__ = "6.0.0-beta.7"
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
class _PersistantData(dict):
    """The app's persistent data."""

    def __init__(self, path):
        super().__init__()
        self.path = path

    def read_possible_values(self, number_of_values):
        """Read and parse the start of a file as if it's JSON formatted.

        Args:
            number_of_values: An int specifying how many values to read.

        Returns:
            A tuple which is either empty or contains at most
            a number of strings equal to number_of_values.
        """

        with open(self.path) as file:
            start_of_file = file.read(8192) or ""
        split_strings = start_of_file.split(",", maxsplit=number_of_values)
        at_least_one_comma_found = len(split_strings) > 1
        del split_strings[-1]
        possible_values = []

        if at_least_one_comma_found:
            for string in split_strings:
                _, key_value_seperator, post_seperator = string.rpartition(": ")
                if key_value_seperator:
                    possible_values.append(post_seperator)
        return tuple(possible_values)

    def read_values_shared_by_an_archive_and_cache(self):
        """Return the shared values from a data file via a short read.

        Returns:
            A tuple (datetime.datetime object, pathlib.Path object)
            containing values shared by an archive and its paired cache.
        """

        number_of_values = 2
        try:
            possible_float, possible_path = self.read_possible_values(number_of_values)
            possible_timestamp = float(possible_float)
            creation_time = datetime.datetime.fromtimestamp(
                possible_timestamp, tz=datetime.timezone.utc
            )
            archived_stating_path = pathlib.Path(possible_path[1:-1])
        except (ValueError, TypeError, OSError, OverflowError):
            raise ValueError("The file didn't contain one or more valid values.")
        return (creation_time, archived_stating_path)


class _Archive(_PersistantData):
    """Storage for paths found in a starting folder."""

    def __init__(self, path):
        super().__init__(path)

    def describe_old_archive(self):
        """If an archive is old return a description of its age."""
        current_time = datetime.datetime.now(datetime.timezone.utc)
        time_between_creation_and_now = current_time - self["creation_time"]
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

    def read_and_set_shared_creation_and_start_values(self):
        """Get crucial values from the storage file via a short read."""
        time, path = self.read_values_shared_by_an_archive_and_cache()
        self["creation_time"] = time
        self["starting_path"] = path

    def read_items_from_file(self, **kwargs):
        """Read and verify the starting folder archive."""
        kwargs_for_open = {"mode": "r", "encoding": "utf-8", "errors": "replace"}
        kwargs_for_open.update(**kwargs)  # Allows override of defaults.
        try:
            with open(self.path, **kwargs_for_open) as archive_file:
                archived = json.load(archive_file)
            archived["creation_time"] = datetime.datetime.fromtimestamp(
                archived["creation_time"], tz=datetime.timezone.utc
            )
            archived["starting_path"] = pathlib.Path(archived["starting_path"])
            archived["sub_paths"] = [
                pathlib.Path(str_path) for str_path in archived["sub_paths"]
            ]
        except (json.JSONDecodeError, KeyError):
            raise _ValidationError("The file you have chosen is not a valid archive.")
        self.update(archived)

    def write_to_file(self, sub_paths, starting_folder, **kwargs):
        """Write the subpaths to the archive's storage file."""
        kwargs_for_open = {"mode": "x", "encoding": "utf-8", "errors": "replace"}
        kwargs_for_open.update(**kwargs)  # Allows override of defaults.
        json_safe_subpaths = [str(path) for path in sub_paths]
        current_time = datetime.datetime.now(datetime.timezone.utc).timestamp()
        json_safe_starting_folder = str(starting_folder.resolve())
        archive = {
            "creation_time": current_time,
            "starting_path": json_safe_starting_folder,
            "sub_paths": json_safe_subpaths,
        }
        with open(self.path, **kwargs_for_open) as json_file:
            json.dump(archive, json_file)


class _Cache(_PersistantData):
    """Storage for the state of a checksum_files function."""

    def __init__(self, path):
        super().__init__(path)

    def read_and_set_shared_creation_and_start_values(self, validation_value=""):
        """Get crucial values from the storage file via a short read."""
        message = (
            "The cache file is holding work which was done on another archive.\n"
            "Please save that work by moving the cache file to another location\n"
            "or simply delete the cache if you no longer need it."
        )
        try:
            time, path = self.read_values_shared_by_an_archive_and_cache()
        except _ValidationError:
            raise _ValidationError(message)
        self["archive_creation_time"] = time
        self["archived_starting_path"] = path
        if validation_value and not self["archive_creation_time"] == validation_value:
            raise _ValidationError(message)

    def read_items_from_file(self, **kwargs):
        """Read the state of a function from the cache file."""
        kwargs_for_open = {"mode": "r", "encoding": "utf-8", "errors": "replace"}
        kwargs_for_open.update(**kwargs)  # Allows override of defaults.
        try:
            with open(self.path, **kwargs_for_open) as cache_file:
                cached = json.load(cache_file)
            cached["archive_creation_time"] = datetime.datetime.fromtimestamp(
                cached["archive_creation_time"], tz=datetime.timezone.utc
            )
            cached["archived_starting_path"] = pathlib.Path(
                cached["archived_starting_path"]
            )
            for key, value in cached["os_errors"].items():
                cached["os_errors"][key] = [
                    (x[0], x[1], datetime.datetime.fromisoformat(x[2])) for x in value
                ]
            cached["paths_and_sums"] = [
                (pathlib.Path(x), y) for x, y in cached["paths_and_sums"]
            ]
        except (json.JSONDecodeError, KeyError):
            message = (
                "The contents of the cache file can no longer be verified.\n"
                "Most likely it was accidentally overwritten by another app.\n"
                "You may wish to check its contents to learn more, or simply"
                " delete the file.\n"
                "Once it's removed you can rerun your last command to"
                " restart the work."
            )
            raise _ValidationError(message)
        self.update(cached)

    def write_to_file(self, paths_and_sums, os_errors, place, **kwargs):
        """Write the state of a function to the cache file.

        Args:
            paths_and_sums: A tuple (path-like object, int).
            os_errors: A dictionary with info on suppressed os errors
            place: An integer representing the last completed checksum.
            **kwargs: Passed to the open function.
        """

        kwargs_for_open = {"mode": "w", "encoding": "utf-8", "errors": "replace"}
        kwargs_for_open.update(**kwargs)  # Allows override of defaults.
        if not paths_and_sums:  # If there are no checksums return early.
            return None
        json_safe_archive_creation_time = self["archive_creation_time"].timestamp()
        json_safe_paths_and_sums = [
            (str(path), checksum) for path, checksum in paths_and_sums
        ]
        json_safe_os_errors = {k: list(v) for k, v in os_errors.items()}
        for key, value in json_safe_os_errors.items():
            json_safe_os_errors[key] = [(x[0], x[1], x[2].isoformat()) for x in value]
        json_safe_archived_starting_path = str(self["archived_starting_path"])
        cache = {
            "archive_creation_time": json_safe_archive_creation_time,
            "archived_starting_path": json_safe_archived_starting_path,
            "place": place,
            "os_errors": json_safe_os_errors,
            "paths_and_sums": json_safe_paths_and_sums,
        }
        with open(self.path, **kwargs_for_open) as cache_file:
            json.dump(cache, cache_file)


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
        counter_value = str(current_index).rjust(self.length_of_total, "0")
        print(
            counter_value,
            self.move_to_start_of_counter,
            file=self.output,
            flush=True,
            sep="",
            end="",
        )

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
        self.print_counter("0")

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
        """Sum the lengths of all the values and return the sum."""
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
                pass []. To print a blank row pass ['', ''].
                The default is ['File', 'Duplicates'].
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


class _ValidationError(Exception):
    """A file storing an _Archive or _Cache obj can't be validated."""

    def __init__(self, message):
        self.message = message


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
        help=(
            "Store the paths found in the starting folder in"
            " a listdupes archive and quit."
        ),
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
        help="Write the results as a JSON file instead of a CSV spreadsheet.",
    )
    parser.add_argument(
        "-p",
        "--progress",
        action="store_true",
        help="Display a progress counter. This may slow things down slightly.",
    )
    parser.add_argument(
        "-r",
        "--read_archive",
        action="store_true",
        help="Read paths from a listdupes archive instead of from a starting folder.",
    )
    args = parser.parse_args(args=overriding_args)
    return args


def _make_file_path_unique(path):
    """Make a similarly named Path object if a path already exists.

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


def _do_pre_checksumming_tasks(
    *,
    paths_to_make,
    main_return_constructor,
    starting_path,
    starting_path_required,
    read_archive,
    write_archive,
    show_progress,
):
    """Give main() the means to either proceed or exit early.

    Since this is a fairly abstract function with many arguments it uses
    required keyword-only arguments to help prevent errors in usage.

    Args:
        paths_to_make: A list of tuples, passed to _make_unique_paths().
        main_return_constructor: Main()'s return value constructor.
        starting_path: An instance of pathlib.Path or its subclasses.
        starting_path_required: A bool.
        read_archive: A bool.
        write_archive: A bool.
        show_progress: A bool.

    Return:
        A named tuple (unique_path, archive, cache, early_exit) where
        'unique_path' is the returned value of _make_unique_paths(),
        'archive' is either None or an _Archive object,
        "cache' is either None or a _Cache object, and
        'early_exit' is a valid return value for main().
    """

    result_tuple = collections.namedtuple(
        "do_pre_checksumming_tasks_return_tuple",
        ["unique_path", "archive", "cache", "early_exit"],
    )

    # Determine the eventual paths of all necessary files.
    try:
        unique_path = _make_unique_paths(paths_to_make)
    except FileExistsError as e:
        return result_tuple(None, None, None, main_return_constructor(str(e), 1))

    # Exit early if a starting path is required and the path is invalid.
    issue_with_starting_path = _starting_path_is_invalid(
        starting_path, read_archive=read_archive
    )
    if issue_with_starting_path and starting_path_required:
        return result_tuple(
            None, None, None, main_return_constructor(issue_with_starting_path, 1)
        )

    # Exit early if the archive or cache aren't valid files
    # or don't belong to each other.
    if read_archive:
        hardcoded_cache_path = pathlib.Path("~", "listdupes_cache").expanduser()
        archive = _Archive(starting_path)
        cache = _Cache(hardcoded_cache_path)
        try:
            archive.read_items_from_file()
            if cache.path.exists():
                # Using the archive's creation time as a quasi-unique ID
                # check that the cache belongs to the archive.
                cache.read_and_set_shared_creation_and_start_values(
                    validation_value=archive["creation_time"]
                )
                # Read the cache in full.
                cache.read_items_from_file()
            else:
                cache["archive_creation_time"] = archive["creation_time"]
                cache["archived_starting_path"] = archive["starting_path"]
        except _ValidationError as e:
            return result_tuple(None, None, None, main_return_constructor(e.message, 1))
        return result_tuple(unique_path, archive, cache, None)

    # Archive subpaths to a file and exit if -a has been passed.
    if write_archive:
        absolute_starting_path = starting_path.resolve()
        sub_paths = _find_sub_paths(
            absolute_starting_path, show_work_message=show_progress
        )
        sorted_sub_paths = sorted(sub_paths)
        archive = _Archive(unique_path.folder_archive)
        archive.write_to_file(sorted_sub_paths, absolute_starting_path)
        message = "The folder has been archived."
        return result_tuple(None, None, None, main_return_constructor(message, 0))

    return result_tuple(unique_path, None, None, None)


def get_checksum_input_values(
    starting_path,
    show_progress,
    archive=None,
    cache=None,
):
    """Return the initial values to pass to a checksum_files function.

    Args:
        starting_path: An instance of pathlib.Path or its subclasses.
        show_progress: A bool indicating whether the path gathering
            function should print a message when it starts.
        archive: Only for internal use. Either None or
            an _Archive object. Defaults to None.
        cache: Only for internal use. Either None or a _Cache object.
            Defaults to None.

    Returns:
        A named tuple (paths, paths_and_sums, os_errors, place).

        'paths' is a list of pathlib.Path objects.

        'paths_and_sums' is a list which is either empty or contains
        tuples of (Path object, int) which pair a Path object and
        the checksum of the associated file.

        'os_errors' is a dictionary with keys for suppressed os errors
        which are mapped to sets which may be empty, or may contain
        tuples of (str, str) pairing a string representation of
        a path with a string describing the error that file raised.

        'place' is an integer representing the index of the last file
        in an archive to be checksummed and cached. If no cache exists
        it defaults to 0.
    """

    result_tuple = collections.namedtuple(
        "get_checksum_input_values_return_tuple",
        ["paths", "paths_and_sums", "os_errors", "place"],
    )
    os_errors = {
        "permission_errors": set(),
        "file_not_found_errors": set(),
        "misc_errors": set(),
    }
    escape_codes = ("\x1b[1m", "\x1b[0m") if sys.stderr.isatty() else ("", "")
    bold, reset_style = escape_codes

    if archive and cache and cache.path.exists():
        old_archive_description = archive.describe_old_archive()
        if old_archive_description:
            print(bold, old_archive_description, reset_style, sep="", file=sys.stderr)
        place_in_sub_paths = cache["place"]
        paths = archive["sub_paths"][place_in_sub_paths:]
        return result_tuple(
            paths, cache["paths_and_sums"], cache["os_errors"], cache["place"]
        )
    elif archive and cache:
        old_archive_description = archive.describe_old_archive()
        if old_archive_description:
            print(bold, old_archive_description, reset_style, sep="", file=sys.stderr)
        paths = archive["sub_paths"]
        return result_tuple(paths, [], os_errors, 0)
    else:
        paths = _find_sub_paths(
            starting_path, show_work_message=show_progress, return_set=show_progress
        )
        return result_tuple(paths, [], os_errors, 0)


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
            contains tuples of (path-like object, int) which pair
            a path with the checksum of the associated file.
        errors_container: A dictionary with keys for suppressed
            os errors mapped to sets which may be empty, or may contain
            tuples of (str, str) pairing a string representation of
            a path with a string describing the error that file raised.
        generator: The generator function taking one positional arg
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
        time = datetime.datetime.now().astimezone()  # Local time.
        file_name = e.filename or str(file_path)
        error_text = e.strerror or ""
        errors_container["permission_errors"].add((file_name, error_text, time))
        return
    except FileNotFoundError as e:
        time = datetime.datetime.now().astimezone()  # Local time.
        file_name = e.filename or str(file_path)
        error_text = e.strerror or ""
        errors_container["file_not_found_errors"].add((file_name, error_text, time))
        _check_path_for_disconnection(file_path)
        return
    except OSError as e:
        time = datetime.datetime.now().astimezone()  # Local time.
        file_name = e.filename or str(file_path)
        error_text = e.strerror or ""
        errors_container["misc_errors"].add((file_name, error_text, time))
        return
    results_container.append((file_path, checksum))


def checksum_files(
    paths,
    paths_and_sums_state,
    os_errors_state,
    place_state=0,
    writer=None,
    sort_key=None,
):
    """Checksum files and return their paths, checksums, and errors.

    Args:
        paths: A container of path-like objects.
        paths_and_sums_state: A container which is either empty or which
            contains tuples of (path-like object, int) which pair
            a path with the checksum of the associated file.
        os_errors_state: A mapping with keys for suppressed os errors
            which are mapped to sets which may be empty, or may contain
            tuples of (str, str) pairing a string representation of
            a path with a string describing the error that file raised.
        place_state: An integer representing the index of the last file
            in an archive to be checksummed and cached.
            If no cache exists it defaults to 0.
        writer: Either None or a callable which takes three arguments,
            as per that passed to search_for_dupes. Defaults to None.
        sort_key: A function for sorting the returned collections.
            The default of None dictates an ascending sort.

    Returns:
        A named tuple (paths_and_sums, os_errors), where
        'paths_and_sums' is a list of tuples which contain a path-like
        object and the checksum integer of the associated file, and
        'os_errors' is a dictionary with info on suppressed os errors.
    """

    result_tuple = collections.namedtuple(
        "checksum_files_return_tuple", ["paths_and_sums", "os_errors"]
    )
    paths_and_sums = paths_and_sums_state
    os_errors = os_errors_state
    place = 0  # Any prior place count is added during finalizing.
    try:
        for index, file_path in enumerate(paths, start=1):
            _checksum_file_and_store_outcome(file_path, paths_and_sums, os_errors)
            place = index
    finally:
        if writer:
            total_place = place_state + place
            writer(paths_and_sums, os_errors, total_place)
    paths_and_sums.sort(key=sort_key)
    os_errors = {k: sorted(v, key=sort_key) for k, v in os_errors.items()}
    return result_tuple(paths_and_sums, os_errors)


def checksum_files_and_show_progress(
    paths,
    paths_and_sums_state,
    os_errors_state,
    place_state=0,
    writer=None,
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
    paths_and_sums = paths_and_sums_state
    os_errors = os_errors_state
    place = 0  # Any prior place count is added during finalizing.
    try:
        checksum_progress.print_text_for_counter()
        for index, file_path in enumerate(paths, start=1):
            _checksum_file_and_store_outcome(file_path, paths_and_sums, os_errors)
            place = index
            checksum_progress.print_counter(index)
    finally:
        if writer:
            total_place = place_state + place
            writer(paths_and_sums, os_errors, total_place)
        checksum_progress.end_count()
    paths_and_sums.sort(key=sort_key)
    os_errors = {k: sorted(v, key=sort_key) for k, v in os_errors.items()}
    return result_tuple(paths_and_sums, os_errors)


def locate_dupes(checksum_result, sort_key=None):
    """Locate duplicate files by comparing their checksums.

    Args:
        checksum_result: A named tuple as per the result of one of
            the two checksum _files functions.
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
            comparisons_progress.print_counter(index + 1)

            for path, checksum in checksum_result.paths_and_sums[index + 1 :]:
                checksums_are_equal = checksum_being_searched == checksum
                if checksums_are_equal and dupes.not_in_values(path_being_searched):
                    dupes[path_being_searched].add(path)
    finally:
        comparisons_progress.end_count()
    dupes.sort_values(sort_key=sort_key)
    return dupes


def search_for_dupes(checksum_input, writer=None, show_progress=False):
    """Search a collection of paths for duplicate files.

    Args:
        checksum_input: A named tuple as per the return value of
            get_checksum_input_values().
        writer: Either None or a callable which takes three arguments.
            1st a container as per a checksum_files function's
            paths_and_sums_state arg, 2nd a mapping as per its
            os_errors_state arg and 3rd an int storing the index of
            the last file checksummed. The writer is called before any
            KeyboardInterrupt is raised, so as to cache
            the function's work. Defaults to None.
        show_progress: A bool indicating whether to display the progress
            of checksumming and comparison processes. Defaults to False.
    Returns:
        A named tuple (dupes, description, return_code), where
        'dupes' is a Dupes object (As per the return value of
        locate_dupes), and 'description' and 'return_code' are
        a string and an integer as per the return of Dupes.status().
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
            writer=writer,
        )
        dupes = locate_dupes_and_show_progress(checksum_result)
    else:
        checksum_result = checksum_files(
            checksum_input.paths,
            checksum_input.paths_and_sums,
            checksum_input.os_errors,
            place_state=checksum_input.place,
            writer=writer,
        )
        dupes = locate_dupes(checksum_result)

    search_status = dupes.status()
    return result_tuple(dupes, search_status.description, search_status.return_code)


def _write_any_errors_to(
    file_path,
    error_mapping,
    labels=["Unread File", "Error Description", "Date Accessed"],
    **kwargs,
):
    """If a mapping of errors has any values log them in a CSV file."""
    kwargs_for_open = {"mode": "x", "encoding": "utf-8", "errors": "replace"}
    kwargs_for_open.update(**kwargs)  # Allows override of defaults.
    if not any(error_mapping.values()):
        return None
    with open(file_path, **kwargs_for_open) as csv_file:
        writer = csv.writer(csv_file)
        if labels and "a" not in kwargs_for_open["mode"]:
            writer.writerow(labels)

        for value in error_mapping.values():
            for path, error_text, time in value:
                # tzname returns the time zone as an abbreviation if
                # the time was provided by the system or
                # as a UTC offset if it was retrieved from a cache file.
                time_zone = time.tzname()
                locale_aware_date_and_time = time.strftime("%x %X")
                error_date_and_time = f"{locale_aware_date_and_time} {time_zone}"
                writer.writerow([path, error_text, error_date_and_time])
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
    paths_to_make = [
        (f"listdupes_output.{output_ext}", "output file"),
        ("listdupes_unread_files_log.csv", "unread files log"),
        ("listdupes_folder_archive.json", "folder archive"),
    ]

    # Do tasks like path validation and running the archive flag,
    # as they need the ability to exit very early.
    unique_path, archive, cache, early_exit = _do_pre_checksumming_tasks(
        paths_to_make=paths_to_make,
        main_return_constructor=result_tuple,
        starting_path=args.starting_folder,
        starting_path_required=starting_path_required,
        read_archive=args.read_archive,
        write_archive=args.archive_folder,
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
        args.starting_folder, args.progress, archive=archive, cache=cache
    )

    # Search for dupes and describe the result to the user.
    writer_arg = cache.write_to_file if cache else None
    search_result = search_for_dupes(
        checksum_input_values, writer=writer_arg, show_progress=args.progress
    )
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
    if args.read_archive and cache.path.exists():
        cache.path.unlink()

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
