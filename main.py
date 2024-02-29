import datetime
import tkinter as tk
import traceback
from pathlib import Path
from shutil import rmtree
from tkinter import messagebox

from requests.exceptions import HTTPError

import google_api
import wordpress
from exceptions import MalformedDataException

TextFields = dict[str, tk.Entry | tk.Text]

row_index = 0


def main():
    tmp_dir = Path("tmp")

    if not tmp_dir.exists():
        tmp_dir.mkdir()

    row_data = google_api.load_sheet("...")

    window, text_fields = initialize_gui()

    # -- Keybinds --
    # Manually load content from URL
    window.bind("<Alt-m>", load_content_from_url(text_fields))
    # Cursor up and down the spreadhseet
    window.bind("<Alt-Left>", load_story(text_fields, row_data, row_offset=-1))
    window.bind("<Alt-Right>", load_story(text_fields, row_data, row_offset=1))
    # Trim the body (i.e. remove the first two lines, usually contains byline)
    window.bind("<Alt-t>", trim_article_body(text_fields))
    # Post article
    window.bind("<Alt-p>", create_post(text_fields))

    try:
        window.mainloop()
    except Exception as e:
        raise e
    finally:
        # Remove temp image files when finished
        rmtree(tmp_dir)


def initialize_gui() -> tuple[tk.Tk, TextFields, tk.Button, tk.Button]:
    """Set up the Tkinter window."""
    window = tk.Tk()
    window.columnconfigure(1, weight=1)

    text_fields = {
        "Headline": tk.Entry,
        "Authors": tk.Entry,
        "Image URL": tk.Entry,
        "Cutline": tk.Entry,
        "Categories": tk.Entry,
        "Content URL": tk.Entry,
        "Content": tk.Text,
    }

    for row, (widget_id, widget) in enumerate(text_fields.items()):
        label_frame = tk.Frame(master=window)
        label_frame.grid(row=row, column=0, padx=10, pady=10)
        label = tk.Label(master=label_frame, text=widget_id)
        label.pack()

        field_frame = tk.Frame(master=window)
        field_frame.grid(row=row, column=1, padx=10, pady=10, sticky="ew")
        widget = widget(master=field_frame)
        widget.pack(fill="x")

        text_fields[widget_id] = widget

    return window, text_fields


def load_story(
    text_fields: TextFields, row_data: google_api.RowData, row_offset: int
) -> callable:
    """Load the story at a given row in the spreadsheet."""

    def inner(_):
        clear_text_boxes(text_fields)

        global row_index

        row_index += row_offset

        story_data = google_api.get_story(row_data, row_index)

        if not story_data:
            return

        html = google_api.google_doc_to_html(story_data["link"])

        text_fields["Authors"].insert("0", story_data["author"])
        text_fields["Image URL"].insert("0", story_data["photo_link"])
        text_fields["Content"].insert("1.0", html)

    return inner


def load_content_from_url(text_fields: TextFields) -> callable:
    """Load the text from a Google Doc into the "Content" field for editing."""

    def inner(_):
        url = text_fields["Content URL"].get()

        if not url:
            return

        html = google_api.google_doc_to_html(url)

        text_fields["Content"].delete("1.0", tk.END)
        text_fields["Content"].insert("1.0", html)

    return inner


def create_post(text_fields: TextFields) -> callable:
    """Parse & upload the article to WordPress."""

    def inner(_):
        try:
            json_data = text_fields_to_json(text_fields)
            wordpress.post(json_data)
        except MalformedDataException as e:
            messagebox.showerror("Malformed or Missing Data", str(e))
            print(traceback.format_exc())
        except HTTPError as e:
            messagebox.showerror("HTTP Error", str(e))
            print(traceback.format_exc())
        except Exception as e:
            messagebox.showerror("General Error", str(e))
            print(traceback.format_exc())
        else:
            clear_text_boxes(text_fields)

    return inner


def text_fields_to_json(text_fields: TextFields) -> dict[str, str]:
    """Convert the raw text data to a JSON object."""
    json_data = {
        "title": text_fields["Headline"].get().strip(),
        "content": text_fields["Content"].get("1.0", "end-1c"),
        "author": wordpress.author_names_to_ids(text_fields["Authors"].get()),
        "categories": wordpress.category_names_to_ids(text_fields["Categories"].get()),
        "featured_media": drive2wordpress(
            text_fields["Image URL"].get(), caption=text_fields["Cutline"].get().strip()
        ),
        "status": "future",
        "date": get_schedule_date(),
    }

    if not (json_data["title"] and json_data["content"]):
        raise MalformedDataException("Title or body is invalid.")

    return json_data


def get_schedule_date() -> datetime.datetime:
    """Generate a `datetime` object representing the nearest Thursday at 7 AM."""
    # https://stackoverflow.com/a/6558571

    today = datetime.date.today()
    thursday = 3  # Sunday == 0
    next_thursday = today + datetime.timedelta((thursday - today.weekday()) % 7)
    return datetime.datetime.combine(next_thursday, datetime.time(hour=7))


def drive2wordpress(url: str, caption: str) -> int | None:
    """Transfer an image from Google Drive to WordPress."""
    if not url:
        return

    filepath = google_api.download_image_from_drive(url)
    media_id = wordpress.upload_media(filepath, caption)
    return media_id


def clear_text_boxes(text_fields: TextFields):
    """Clear all text boxes in the GUI."""
    for widget in text_fields.values():
        if type(widget) is tk.Entry:
            widget.delete(0, tk.END)
        else:
            widget.delete("1.0", tk.END)


def trim_article_body(text_fields: TextFields) -> callable:
    """Delete the first two lines of the article body.
    These lines usually list the author and their title, which should not go in the body.
    """

    def inner(_):
        text_fields["Content"].delete("1.0", "3.0")

    return inner


if __name__ == "__main__":
    main()
