import os.path
import re
from pathlib import Path
from typing import Optional

import googleapiclient.discovery
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def authenticate(platform: str, version: str) -> googleapiclient.discovery.Resource:
    """Authenticates with Google Drive and returns a Resource object."""
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build(platform, version, credentials=creds)

def isolate_document_id(url: str) -> Optional[str]:
    return re.search("(?<=/d/)(.*?)(?=/)", url).group()

def google_doc_to_html(url: str) -> str:
    """Download the raw HTML data from a Google Doc."""
    service = authenticate("docs", "v1")
    document_id = isolate_document_id(url)
    document = service.documents().get(documentId=document_id).execute()
    body = document.get("body")

    html = ""

    for block in body.get("content"):
        # Skip line if not a paragraph
        if "paragraph" not in block.keys():
            continue

        paragraph_body = ""

        for element in block.get("paragraph").get("elements"):
            text_run = element.get("textRun")

            if not text_run:
                continue

            opening_tag = ""
            closing_tag = ""

            if "bold" in text_run.get("textStyle").keys():
                opening_tag = "<strong>"
                closing_tag = "</strong>"

            if "italic" in text_run.get("textStyle").keys():
                opening_tag = "<em>"
                closing_tag = "</em>"

            if "link" in text_run.get("textStyle").keys():
                opening_tag = (
                    f"<a href='{text_run.get('textStyle').get('link').get('url')}'>"
                )
                closing_tag = "</a>"

            content = text_run.get("content")

            # If the content contains text and ends with a newline, it is the end of a paragraph
            end_of_paragraph = "\n" in content.lstrip()

            content = content.strip()

            if not content:
                continue

            opens_quote = content[-1] in ["“", '"']

            # Workaround for the API occasionally ending a textRun in the middle of a sentence
            if not (end_of_paragraph or opens_quote):
                content += " "

            paragraph_body += opening_tag
            paragraph_body += content
            paragraph_body += closing_tag

        if not paragraph_body:
            continue

        html += "<p>"
        html += paragraph_body
        html += "</p>\n"

    # Remove extraneous whitespace
    html = html.strip()
    return html


def download_image_from_drive(url: str) -> Path:
    """Download an image from Google Drive."""
    service = authenticate("drive", "v3")
    file_id = url.split("/")[-2]
    request = service.files().get_media(fileId=file_id)
    metadata = service.files().get(fileId=file_id).execute()

    output_file = Path("tmp", metadata.get("name"))

    with open(output_file, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while done is False:
            _, done = downloader.next_chunk()

    return output_file


RowData = list[dict[str, list[dict]]]
StoryDetails = dict[str, str]


def load_sheet(_id: str) -> RowData:
    """Get the rows of a Google Sheet."""
    try:
        service = authenticate("sheets", "v4")
        sheet = service.spreadsheets()
        result = sheet.get(
            spreadsheetId=_id,
            ranges="Sheet1!A1:O100",
            fields="sheets/data/rowData/values",
        ).execute()
        row_data = result["sheets"][0]["data"][0]["rowData"]
    except (HttpError, ValueError, IndexError) as err:
        print(err)
    return row_data


def get_story(row_data: RowData, row_index: int) -> Optional[StoryDetails]:
    """Get the Docs URL, author, and photo URL for a given story.
    Returns `None` if the specified row is not a story."""

    LINK = 4
    WORD_COUNT = 6
    AUTHOR = 7
    PHOTO_LINK = 13

    def is_story(row):
        # No word count = not a story
        return row and row["values"][WORD_COUNT].get("formattedValue", "").isdecimal()

    row = row_data[row_index]

    if not is_story(row):
        return None

    values = row["values"]

    return {
        "link": values[LINK].get("hyperlink", ""),
        "author": values[AUTHOR].get("formattedValue", ""),
        "photo_link": values[PHOTO_LINK].get("hyperlink", ""),
    }
