
### Listdupes is a Python Script Which Checks a Folder for Duplicate Files

The program saves its list of duplicates as a spreadsheet. Even collections of
hundreds of thousands of files can be checked, so if you've got a giant folder
or an external drive to check you can turn on listdupes' progress counter
and watch it speed through the files.

Note that, while the program uses a standard method called checksumming 
to determine if files are identical, **false matches do occur with
checksumming**. Confirm listdupes' findings manually before you choose
to delete any critical data.

#### Features

*   Nothing else to install besides Python
*   Helpful error messages for people new to command-line programs
*   Unix-style behavior for people with experience
*   Optional progress counter
*   Filter functionality for advanced use cases

#### Examples of Use

Search a folder and its subfolders for duplicates:  
`/path/to/listdupes.py /Users/adira/Music`

Search an external drive and show a progress counter:  
`/path/to/listdupes.py --progress /Volumes/FlashDrive`

Act as a filter (e.g. grep), processing input from stdin and sending it to stdout:  
`/path/to/listdupes.py --filter < ~/list_of_network_drives.txt > ~/Desktop/output_file.csv`

New to the command-line? Be sure to wrap paths in quotes if they contain any spaces:  
`/path/to/listdupes.py "/Users/adira/Documents/Technical Manuals"`

#### Installation

To install the program download [the latest release][1] as a zip file.
Unzip the file and place the listdupes folder wherever you'd like.
Once this is done you can see the program's help message and view its 
features by entering the following command in your terminal:  
`/path/to/listdupes.py --help`  
(Remember to replace `/path/to/` with the path to listdupes.py. On macOS you can drag and drop the file in the terminal window to enter the path.)

If the program won't run you may need to install Python. You can [find it here][2].

##### Tip for macOS, Linux & Unix

If Python is installed and listdupes still won't run you may need to give 
the file permission to run as a program. Type the following command into
your terminal and press Return:  
`chmod 744 /path/to/listdupes.py`

#### Acknowledgments

The script was developed with Python 3.9 on macOS 12 and written
using [the Nova code editor][3].

Initially developed during Pride Month in '22, listdupes is dedicated to
[Lynn Conway][4], [Sophie Wilson][5], and [Mary Ann Horton][6],
trans giants of computer history.

[1]: https://github.com/Chris-Dobbins/listdupes/releases/latest  "Download listdupes"
[2]: https://www.python.org/downloads/  "Download Python"
[3]: https://nova.app  "Learn about Nova"
[4]: https://en.wikipedia.org/wiki/Lynn_Conway  "Lynn Conway on Wikipedia"
[5]: https://en.wikipedia.org/wiki/Sophie_Wilson  "Sophie Wilson on Wikipedia"
[6]: https://en.wikipedia.org/wiki/Mary_Ann_Horton  "Mary Ann Horton on Wikipedia"
