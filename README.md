
### Listdupes is a Python Script Which Checks a Folder for Duplicate Files

The script saves its list of duplicates as a spreadsheet. Even collections of
hundreds of thousands of files can be checked, although this typically takes
hours. If you've got a large folder to check you can turn on listdupes'
progress counter and watch it speed through the files.

Note that, while the script uses an industry standard method called checksumming 
to determining if files are identical, **false matches do occur with
checksumming**. Confirm listdupes' findings manually before you choose
to delete any critical data.

#### Installation

To install, download [the latest release][1] as a zip file.
Unzip the file and place the listdupes folder wherever you'd like.
Then, to give the script permission to run as a program, type the following command
into your terminal and press Return:
`chmod 744 /path/to/file/listdupes.py`

If the script won't run you may need to install Python. You can [find it here][2].

Once this is all done you can see the script's help message and view its 
features and options by entering the following command:
`/path/to/file/listdupes.py --help`

#### Project Goals

The script aims to be as lightweight as possible; a single Python file
with no modules to download or other external dependencies. It also strives
to strike a good balance between being a friendly tool for beginners,
a useful *nix command, and a useful Python module. Feature requests are encouraged.

#### Acknowledgments

The script was developed with Python 3.9 on macOS 12 and written
using [the Nova code editor][3].

Developed during Pride Month, listdupes is dedicated to
[Lynn Conway][4], [Sophie Wilson][5], and [Mary Ann Horton][6],
trans giants of computer history.

[1]: https://github.com/Chris-Dobbins/listdupes/releases/latest  "Download listdupes"
[2]: https://www.python.org/downloads/  "Download Python"
[3]: https://nova.app  "Learn about Nova"
[4]: https://en.wikipedia.org/wiki/Lynn_Conway  "Lynn Conway on Wikipedia"
[5]: https://en.wikipedia.org/wiki/Sophie_Wilson  "Sophie Wilson on Wikipedia"
[6]: https://en.wikipedia.org/wiki/Mary_Ann_Horton  "Mary Ann Horton on Wikipedia"
