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
    "posts": f"https://{consts.domain_name}/wp-json/wp/v2/posts",
    "media": f"https://{consts.domain_name}/wp-json/wp/v2/media",
    "users": f"https://{consts.domain_name}/wp-json/wp/v2/users",
    "categories": f"https://{consts.domain_name}/wp-json/wp/v2/categories",
}


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
        matches = requests.get(
            url=f"{endpoints['categories']}?search={name}",
            timeout=REQUEST_TIMEOUT_SECONDS,
        ).json()

        if not matches:
            raise MalformedDataException(f'No category matches "{name}"')

        category = None

        for match in matches:
            if match["name"].lower() == name.lower():
                category = match
                break

        if not category:
            raise MalformedDataException(
                f'No category exactly matches "{name}", but similar results were found'
            )

        ids.append(category["id"])
        parent_id: int = category["parent"]

        # Automatically include parent categories as well
        while parent_id != 0:
            parent_category = requests.get(
                url=f"{endpoints['categories']}/{parent_id}",
                timeout=REQUEST_TIMEOUT_SECONDS,
            ).json()
            ids.append(parent_category["id"])
            parent_id = parent_category["parent"]

    return ",".join([str(_id) for _id in ids])


def author_names_to_ids(name_raw: str) -> str:
    """Takes an author names and returns a string of the corresponding
    numeric ID for use with the WordPress API.
    Author names are not case-sensitive.


    Does not currently support multiple authors."""

    if not name_raw:
        raise MalformedDataException("No authors provided.")

    name = name_raw.strip()
    matches = requests.get(
        url=f"{endpoints['users']}?search={name}",
        timeout=REQUEST_TIMEOUT_SECONDS,
    ).json()

    # Create new author if they don't already exist
    if not matches:
        return str(add_new_author(name))

    author = None

    for match in matches:
        if match["name"].lower() == name.lower():
            author = match
            break

    if not author:
        raise MalformedDataException(
            f'No author exactly matches "{name}", but similar results were found'
        )

    return author["id"]


def add_new_author(name: str) -> int:
    """Add a new author to the WordPress site.
    Returns the new user's ID."""

    # First name is classified as every name, separated by spaces, excluding
    # the very last
    first = " ".join(name.split(" ")[:-1])
    first_initial = first[0]
    last = name.split(" ")[-1]
    author_username = first_initial.lower() + last.lower()
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
