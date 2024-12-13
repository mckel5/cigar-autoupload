import json
import secrets
from pathlib import Path
import requests
from PIL import Image
from pillow_heif import register_heif_opener

import consts
from exceptions import MalformedDataException

# Timeout for all HTTP requests, including media upload/download
REQUEST_TIMEOUT_SECONDS = 60

# Allow processing of HEIC/HEIF (iPhone) images
register_heif_opener()

endpoints = {
    "posts": f"https://{consts.domain_name}/wp-json/wp/v2/posts/",
    "media": f"https://{consts.domain_name}/wp-json/wp/v2/media/",
    "users": f"https://{consts.domain_name}/wp-json/wp/v2/users/",
    "categories": f"https://{consts.domain_name}/wp-json/wp/v2/categories/",
}

CATEGORIES = requests.get(
    url=f"{endpoints['categories']}?per_page=100", timeout=REQUEST_TIMEOUT_SECONDS
).json()


def post(json_data: dict[str, str]) -> None:
    """Post an article to WordPress."""
    response = requests.post(
        url=endpoints["posts"],
        data=json_data,
        auth=(consts.username, consts.password),
        headers=consts.request_headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()


def upload_media(path: Path, caption: str = None) -> int:
    """Upload an image to WordPress and return the media ID."""
    path = convert_image_format(path)
    media = {"file": open(path, "rb")}
    data = {"caption": caption}
    response = requests.post(
        url=endpoints["media"],
        data=data,
        files=media,
        auth=(consts.username, consts.password),
        headers=consts.request_headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["id"]


def convert_image_format(path: Path) -> Path:
    """Convert an image to JPG if it is not either JPG or PNG."""
    image = Image.open(path)
    if image.format not in ["JPG", "PNG"]:
        path = path.with_suffix(".jpg")
        image.save(path)
    return path


def category_names_to_ids(names_raw: str) -> str:
    """Takes a string of category names (separated by `;`),
    and returns a string of the corresponding numeric IDs (separated by `,`)
    for use with the WordPress API.
    Category names are not case-sensitive."""
    if not names_raw:
        raise MalformedDataException("No categories provided.")

    names = names_raw.split(";")
    ids = []

    for name in names:
        name = name.strip()
        try:
            # `filter` returns an iterable, so use `next` to get the element inside
            # pylint: disable=cell-var-from-loop
            category = next(
                filter(lambda c: c["name"].lower() == name.lower(), CATEGORIES)
            )
        except StopIteration as e:
            raise MalformedDataException(f'No category matching "{name}"') from e
        ids.append(category["id"])
        parent_id = category["parent"]
        while parent_id:
            # pylint: disable=cell-var-from-loop
            parent_category = next(filter(lambda c: c["id"] == parent_id, CATEGORIES))
            ids.append(parent_category["id"])
            parent_id = parent_category["parent"]
    return ",".join([str(_id) for _id in ids])


def author_names_to_ids(names: str) -> str:
    """Takes a string of author names (separated by `;`
    and returns a string of the corresponding numeric IDs (separated by `,`)
    for use with the WordPress API.
    Author names are not case-sensitive."""
    if not names:
        raise MalformedDataException("No authors provided.")

    # TODO: get from API rather than json file
    # requires "pagination" and may not be worth it

    names_list = names.split(";")
    ids = []
    with open("authors.json", "r", encoding="utf-8") as f:
        authors = json.load(f)
        for name in names_list:
            name = name.strip()
            try:
                # pylint: disable=cell-var-from-loop
                author = next(
                    filter(lambda a: a["display_name"].lower() == name.lower(), authors)
                )
                ids.append(author["ID"])
            except StopIteration:
                _id = str(add_new_author(name))
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

    response = requests.post(
        endpoints["users"],
        data=data,
        auth=(consts.username, consts.password),
        headers=consts.request_headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    with open("authors.json", "r", encoding="utf-8") as f:
        json_data = json.load(f)

    json_data.append({"ID": str(response.json()["id"]), "display_name": name})

    with open("authors.json", "w", encoding="utf-8") as f:
        json.dump(json_data, f)

    return response.json()["id"]
