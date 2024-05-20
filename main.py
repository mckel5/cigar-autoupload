import datetime
import tkinter as tk
import traceback
from pathlib import Path
from shutil import rmtree
from tkinter import messagebox
from typing import Optional
import threading

from requests.exceptions import HTTPError

import google_api
import wordpress
from exceptions import MalformedDataException

TextFields = dict[str, tk.Entry | tk.Text]

row_index: int
row_data: google_api.RowData


def main():
    tmp_dir = Path("tmp")

    if not tmp_dir.exists():
        tmp_dir.mkdir()

    global row_index, row_data
    row_index = 0
    row_data = prompt_for_spreadsheet()

    window, text_fields = initialize_gui()

    # -- Keybinds --
    # Manually load content from URL
    window.bind("<Alt-m>", load_content_from_url(text_fields))
    # Cursor up and down the spreadhseet
    window.bind("<Alt-Up>", load_story(text_fields, row_offset=-1))
    window.bind("<Alt-Down>", load_story(text_fields, row_offset=1))
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


def prompt_for_spreadsheet() -> google_api.RowData:
    """Set up the Tkinter window."""

    window = tk.Tk()
    window.geometry("800x100")

    # label_frame = tk.Frame(master=window)
    # label_frame.grid(row=0, padx=10, pady=10)
    label = tk.Label(master=window, text="Enter spreadsheet URL:")
    label.pack()

    # field_frame = tk.Frame(master=window)
    # field_frame.grid(row=1, padx=10, pady=10)
    widget = tk.Entry(master=window)
    widget.pack(fill=tk.X, expand=True)

    spreadsheet_id = None

    def get_spreadsheet_url(entry: tk.Entry) -> callable:
        def inner(_):
            url = entry.get()
            if url:
                nonlocal spreadsheet_id
                spreadsheet_id = google_api.isolate_document_id(url)
                window.destroy()
            else:
                messagebox.showerror("Invalid URL entered")
                return

        return inner

    window.bind("<Return>", get_spreadsheet_url(widget))
    window.mainloop()

    return google_api.load_sheet(spreadsheet_id)


def initialize_gui() -> tuple[tk.Tk, TextFields]:
    """Set up the Tkinter window."""
    window = tk.Tk()
    window.columnconfigure(1, weight=1)

    text_fields = {
        "Headline": tk.Entry,
        "Cutline": tk.Entry,
        "Categories": tk.Entry,
        "Authors": tk.Entry,
        "Image URL": tk.Entry,
        "Content": tk.Text,
        "(Content URL Override)": tk.Entry,
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


def load_story(text_fields: TextFields, row_offset: int) -> callable:
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
        url = text_fields["(Content URL Override)"].get()

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

            if not (json_data["title"] and json_data["content"]):
                raise MalformedDataException("Title or body is invalid.")

            # Uploading media is typically a blocking operation that can take 15+ seconds.
            # To remedy this, we make uploading a threaded background job so that the next article
            # can be prepared in the meantime.

            image_url = text_fields["Image URL"].get()
            cutline = text_fields["Cutline"].get().strip()

            class UploaderThread(threading.Thread):
                def run(self):
                    json_data["featured_media"] = drive2wordpress(
                        url=image_url,
                        caption=cutline,
                    )

                    # print(image_url, cutline)
                    wordpress.post(json_data)

            post_thread = UploaderThread()
            post_thread.start()

        except MalformedDataException as e:
            messagebox.showerror(title="Malformed or Missing Data", message=str(e))
            print(traceback.format_exc())
        except HTTPError as e:
            messagebox.showerror(title="HTTP Error", message=str(e))
            print(traceback.format_exc())
        except Exception as e:
            messagebox.showerror(title="General Error", message=str(e))
            print(traceback.format_exc())
        else:
            load_story(text_fields, row_offset=1)(_)

    return inner


def text_fields_to_json(text_fields: TextFields) -> dict[str, str]:
    """Convert the raw text data from the GUI to a JSON object."""
    return {
        "title": text_fields["Headline"].get().strip(),
        "content": text_fields["Content"].get("1.0", "end-1c"),
        "author": wordpress.author_names_to_ids(text_fields["Authors"].get()),
        "categories": wordpress.category_names_to_ids(text_fields["Categories"].get()),
        "status": "future",
        "date": get_schedule_date(),
    }


def get_schedule_date() -> datetime.datetime:
    """Generate a `datetime` object representing the nearest Thursday at 7 AM."""
    # https://stackoverflow.com/a/6558571

    today = datetime.date.today()
    thursday = 3  # Sunday == 0
    next_thursday = today + datetime.timedelta((thursday - today.weekday()) % 7)
    return datetime.datetime.combine(next_thursday, datetime.time(hour=8))


def drive2wordpress(url: str, caption: str) -> Optional[int]:
    """Transfer an image from Google Drive to WordPress.
    Returns the ID of the media provided by Wordpress."""
    if not url:
        return None

    filepath = google_api.download_image_from_drive(url)
    media_id = wordpress.upload_media(filepath, caption)
    return media_id


def clear_text_boxes(text_fields: TextFields):
    """Clear all text boxes in the GUI."""
    for widget in text_fields.values():
        if isinstance(widget, tk.Entry):
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
