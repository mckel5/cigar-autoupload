import datetime
import tkinter as tk
from pathlib import Path
from shutil import rmtree
from tkinter import messagebox

import google_api
import wordpress
from exceptions import HttpRequestException, MalformedDataException


def main():
    tmp_dir = Path("tmp")

    if not tmp_dir.exists():
        tmp_dir.mkdir()
    window, text_fields, load_content_btn, post_btn = initialize_gui()
    window.bind("<Control-Return>", create_post(text_fields))
    load_content_btn.bind("<Button-1>", load_content_from_url(text_fields))
    post_btn.bind("<Button-1>", create_post(text_fields))
    try:
        window.mainloop()
    except Exception as e:
        raise e
    finally:
        rmtree(tmp_dir)


def initialize_gui() -> tuple[tk.Tk, dict[str, tk.Entry | tk.Text], tk.Button, tk.Button]:
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
        widget.pack(fill='x')

        text_fields[widget_id] = widget

    load_content_btn = tk.Button(master=window, text="Load content from URL")
    load_content_btn.grid(row=window.grid_size()[1] + 1, column=0, sticky="ew")

    post_btn = tk.Button(master=window, text="Post")
    post_btn.grid(row=window.grid_size()[1] + 1, column=1, sticky="ew")

    return window, text_fields, load_content_btn, post_btn


def load_content_from_url(text_fields: dict[str, tk.Entry | tk.Text]) -> callable:
    """Load the text from a Google Doc into the "Content" field for editing."""

    def inner(_):
        url = text_fields["Content URL"].get()

        if not url:
            return

        html = google_api.google_doc_to_html(url)

        text_fields["Content"].delete("1.0", tk.END)
        text_fields["Content"].insert("1.0", html)

    return inner


def create_post(text_fields: dict[str, tk.Entry | tk.Text]) -> callable:
    """Parse & upload the article to WordPress."""

    def inner(_):
        try:
            json_data = text_fields_to_json(text_fields)
            wordpress.post(json_data)
        except MalformedDataException as e:
            messagebox.showerror("Malformed or Missing Data", str(e))
        except HttpRequestException as e:
            messagebox.showerror("HTTP Error", str(e))
        except Exception as e:
            messagebox.showerror("General Error", str(e))
        else:
            for widget in text_fields.values():
                if type(widget) is tk.Entry:
                    widget.delete(0, tk.END)
                else:
                    widget.delete("1.0", tk.END)
            # messagebox.showinfo("Success!")

    return inner


def text_fields_to_json(text_fields: dict[str, tk.Entry | tk.Text]) -> dict[str, str]:
    """Convert the raw text data to a JSON object."""
    json_data = {
        "title": text_fields["Headline"].get().strip(),
        "content": text_fields["Content"].get("1.0", "end-1c"),
        "author": wordpress.author_names_to_ids(text_fields["Authors"].get()),
        "categories": wordpress.category_names_to_ids(text_fields["Categories"].get()),
        "featured_media": drive2wordpress(text_fields["Image URL"].get(), caption=text_fields["Cutline"].get().strip()),
        "status": "future",
        "date": get_schedule_date(),
    }

    if not (json_data["title"] and json_data["content"]):
        raise MalformedDataException("Title or body is invalid.")

    return json_data


def get_schedule_date() -> datetime.datetime:
    """Generate a datetime object representing next Thursday at 6 AM."""
    # https://stackoverflow.com/a/6558571

    today = datetime.date.today()
    thursday = 3  # Sunday = 0
    next_thursday = today + datetime.timedelta((thursday - today.weekday()) % 7)
    return datetime.datetime.combine(next_thursday, datetime.time(hour=6))


def drive2wordpress(url: str, caption: str) -> int | None:
    """Transfer an image from Google Drive to WordPress."""
    if not url:
        return

    filepath = google_api.download_image_from_drive(url)
    media_id = wordpress.upload_media(filepath, caption)
    return media_id


if __name__ == '__main__':
    main()
