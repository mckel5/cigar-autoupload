import datetime
import json
import tkinter as tk
from pathlib import Path
from shutil import rmtree
from tkinter import messagebox

import markdown
import requests
from PIL import Image
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

import consts

posts_url = "https://rhodycigar.com/wp-json/wp/v2/posts/"
media_url = "https://rhodycigar.com/wp-json/wp/v2/media/"
tmp_dir = Path("tmp/")

username = consts.username
password = consts.password


class HttpRequestException(Exception):
    pass


class MalformedDataException(Exception):
    pass


def main():
    if not tmp_dir.exists():
        tmp_dir.mkdir()
    window, text_fields, post_btn = initialize_gui()
    window.bind("<Control-Return>", create_post(text_fields))
    post_btn.bind("<Button-1>", create_post(text_fields))
    try:
        window.mainloop()
    except Exception as e:
        raise e
    finally:
        rmtree(tmp_dir)


def initialize_gui() -> tuple[tk.Tk, dict[str, tk.Entry | tk.Text], tk.Button]:
    """Set up the Tkinter window"""
    window = tk.Tk()
    window.columnconfigure(1, weight=1)

    text_fields = {
        "Headline": tk.Entry,
        "Author ID": tk.Entry,
        "Image URL": tk.Entry,
        "Cutline": tk.Entry,
        "Categories": tk.Entry,
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

    post_btn = tk.Button(master=window, text="Post")
    post_btn.grid(row=window.grid_size()[1] + 1, column=0, sticky="ew", columnspan=2)

    return window, text_fields, post_btn


def create_post(text_fields: dict[str, tk.Entry | tk.Text]) -> callable:
    """Upload the article to WordPress"""

    def inner(_):
        try:
            json_data = text_fields_to_json(text_fields)
            # send_http_request(posts_url, json_data)
            response = requests.post(url=posts_url, data=json_data, auth=(username, password))
            if not response.ok:
                raise HttpRequestException(response.json())
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
    """Convert the raw text data to a JSON object"""
    json_data = {
        "title": text_fields["Headline"].get(),
        "content": markdown.markdown(text_fields["Content"].get("1.0", "end-1c").replace("\n", "\n\n")),
        "author": text_fields["Author ID"].get(),
        "categories": category_names_to_ids(text_fields["Categories"].get()),
        "featured_media": drive2wordpress(text_fields["Image URL"].get(), caption=text_fields["Cutline"].get()),
        "status": "future",
        "date": get_schedule_date(),
    }

    if not (json_data["title"] and json_data["content"] and json_data["author"]):
        raise MalformedDataException("Title, body, or author is invalid.")

    return json_data


def get_schedule_date() -> datetime.datetime:
    """Generate a datetime object representing next Thursday at 6 AM."""
    today = datetime.date.today()
    # https://stackoverflow.com/a/6558571
    # 3 represents Thursday in terms of datetime weekdays
    next_thursday = today + datetime.timedelta((3 - today.weekday()) % 7)
    return datetime.datetime.combine(next_thursday, datetime.time(hour=6))


def download_image_from_drive(url: str) -> (str, str):
    gauth = GoogleAuth()
    gauth.LocalWebserverAuth()
    drive = GoogleDrive(gauth)

    file_id = url.split("/")[-2]
    remote_file = drive.CreateFile({"id": file_id})
    # Image must be saved to a tmp file, as pydrive does not retrieve metadata (including filename) until *after* the
    # image is downloaded
    local_filepath = tmp_dir / "tmp"
    remote_file.GetContentFile(str(local_filepath))
    new_filename = remote_file.metadata['title']
    # os.rename(f"{parent_dir}/tmp", f"{parent_dir}/{filename}")
    local_filepath = local_filepath.rename(local_filepath.with_name(new_filename))
    return local_filepath


def upload_media(path: Path, caption: str = None) -> int:
    """Upload an image to WordPress and return the media ID."""
    path = convert_image_format(path)
    media = {'file': open(path, "rb")}
    data = {'caption': caption}
    response = requests.post(url=media_url, data=data, files=media, auth=(username, password))
    if not response.ok:
        raise HttpRequestException(response.json())
    return response.json()["id"]


def convert_image_format(path: Path) -> Path:
    """Convert an image to JPG if it is not either JPG or PNG."""
    image = Image.open(path)
    if image.format not in ["JPG", "PNG"]:
        path = path.with_suffix(".jpg")
        image.save(path)
    return path


def drive2wordpress(url: str, caption: str) -> int | None:
    """Transfer an image from Google Drive to WordPress."""
    if not url:
        return

    filepath = download_image_from_drive(url)
    media_id = upload_media(filepath, caption)
    return media_id


def category_names_to_ids(names: str) -> str:
    """Takes a string of category names, separated by commas, and returns a string of the corresponding numeric IDs.
    Category names are not case-sensitive."""
    if not names:
        raise MalformedDataException("No categories provided.")

    names_list = names.split(",")
    ids = []
    with open("categories.json", "r") as f:
        categories = json.load(f)
        for name in names_list:
            name = name.strip()
            try:
                # `filter` returns an iterable, so use `next` to get the element inside
                category = next(filter(lambda c: c["name"].lower() == name.lower(), categories))
            except StopIteration:
                raise MalformedDataException(f"No category matching \"{name}\"")
            ids.append(category["id"])
            parent_id = category["parent"]
            while parent_id:
                parent_category = next(filter(lambda c: c["id"] == parent_id, categories))
                ids.append(parent_category["id"])
                parent_id = parent_category["parent"]
    return ",".join([str(_id) for _id in set(ids)])


if __name__ == '__main__':
    main()
