listdupes is a command-line application which allows you to check 
a folder and its subfolders for duplicate files. You can access
the app's help message and view its features and options by typing
the following into your terminal:

/path/to/file/listdupes.py --help

Note that while the app uses an industry standard checksumming method
for determining if files are identical, false matches do occur with
checksumming. Confirm listdupe's findings manually before you choose
to delete any critical data.

listdupes aims to be as lightweight as possible; a single python file
with no external dependencies. Feature requests are encouraged.

The script was developed with Python 3.9 on macOS 12 and written
using the Nova code editor by Panic Inc. https://nova.app

Developed during Pride Month, listdupes is dedicated to Lynn Conway,
Sophie Wilson, and Mary Ann Horton, trans giants of computer history.
