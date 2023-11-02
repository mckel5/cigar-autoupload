import json
import secrets
from pathlib import Path

import requests
from PIL import Image

import consts
from exceptions import MalformedDataException

posts_url = f"https://{consts.domain_name}/wp-json/wp/v2/posts/"
media_url = f"https://{consts.domain_name}/wp-json/wp/v2/media/"
users_url = f"https://{consts.domain_name}/wp-json/wp/v2/users/"


def post(json_data: dict[str, str]) -> None:
    """Post an article to WordPress."""
    response = requests.post(url=posts_url, data=json_data, auth=(consts.username, consts.password),
                             headers=consts.request_headers)
    response.raise_for_status()


def upload_media(path: Path, caption: str = None) -> int:
    """Upload an image to WordPress and return the media ID."""
    path = convert_image_format(path)
    media = {'file': open(path, "rb")}
    data = {'caption': caption}
    response = requests.post(url=media_url, data=data, files=media, auth=(consts.username, consts.password),
                             headers=consts.request_headers)
    response.raise_for_status()
    return response.json()["id"]


def convert_image_format(path: Path) -> Path:
    """Convert an image to JPG if it is not either JPG or PNG."""
    image = Image.open(path)
    if image.format not in ["JPG", "PNG"]:
        path = path.with_suffix(".jpg")
        image.save(path)
    return path


def category_names_to_ids(names: str) -> str:
    """Takes a string of category names, separated by semicolons (;), and returns a string of the corresponding numeric IDs.
    Category names are not case-sensitive."""
    if not names:
        raise MalformedDataException("No categories provided.")

    # TODO: also use API, though not strictly necessary

    names_list = names.split(";")
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


def author_names_to_ids(names: str) -> str:
    """Takes a string of author names, separated by semicolons (;), and returns a string of the corresponding numeric IDs.
    Author names are not case-sensitive."""
    if not names:
        raise MalformedDataException("No authors provided.")

    # TODO: get from API rather than json file
    # requires "pagination" and may not be worth it

    names_list = names.split(";")
    ids = []
    with open("authors.json", "r") as f:
        authors = json.load(f)
        for name in names_list:
            name = name.strip()
            try:
                # `filter` returns an iterable, so use `next` to get the element inside
                author = next(filter(lambda a: a["display_name"].lower() == name.lower(), authors))
                ids.append(author["ID"])
            except StopIteration:
                # raise MalformedDataException(f"No author matching \"{name}\"")
                _id = add_new_author(name)
                ids.append(_id)
    return ",".join(ids)


def add_new_author(name: str) -> int:
    """Add a new author to the WordPress site."""
    first = " ".join(name.split(" ")[:-1])
    last = name.split(" ")[-1]
    author_username = first[0].lower() + last.lower()
    email = author_username + "@nogood.net"
    author_password = secrets.token_urlsafe(24)

    data = {
        "username": author_username,
        "name": name,
        "first_name": first,
        "last_name": last,
        "email": email,
        "nickname": author_username,
        "password": author_password,
    }

    response = requests.post(users_url, data=data, auth=(consts.username, consts.password),
                             headers=consts.request_headers)
    response.raise_for_status()

    with open("authors.json", "r") as f:
        json_data = json.load(f)

    json_data.append({
        "ID": str(response.json()["id"]),
        "display_name": name
    })

    with open("authors.json", "w") as f:
        json.dump(json_data, f)

    return response.json()["id"]
