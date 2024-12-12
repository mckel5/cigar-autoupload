# Rhody Cigar Autoupload

This project is designed to streamline the process of publishing articles each week on the [Good Five Cent Cigar](https://rhodycigar.com), the University of Rhode Island's school newspaper. It autofills as much information as possible from each week's editorial spreadsheet and abstracts the process of publishing to WordPress.

## Setup

1. Clone the project
1. Download `credentials.json` from Google Cloud Console and place it in the project's root directory
    - You must have access to the Google Cloud project for this
    - Your Google credentials will be saved after the first time you log in, preventing excessive OAuth popups
1. Create a `consts.py` file containing the following variables:
    - `username` (WordPress username)
    - `password` (auto-generated application password)
    - `domain_name` (domain name of your WordPress site, e.g. "rhodycigar.com")
1. Install all dependencies listed in `requirements.txt`
    - It's recommended to set up virtual Python environment for this
    - Tkinter may need to be installed through your system's package manager (or otherwise globally)
1. Run `main.py` and a Tkinter window will appear

## Keybinds

`Alt` + `Down`: Cursor down one row in the spreadsheet

`Alt` + `Up`: Cursor up one row in the spreadsheet

`Alt` + `T`: **T**rim the first two rows from the article content (usually the author's name and position, but check first!)

`Alt` + `P`: **P**ost an article (automatically cursors down one row afterward)

`Alt` + `M`: **M**anually load an article from a Google Doc URL pasted in the "Content URL Override" field