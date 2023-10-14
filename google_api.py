# from __future__ import print_function

import os.path
import re
from pathlib import Path

import googleapiclient.discovery
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']


def authenticate(platform: str, version: str) -> googleapiclient.discovery.Resource:
    """Authenticates with Google Drive and returns a Resource object."""
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build(platform, version, credentials=creds)


def google_doc_to_html(url: str) -> str:
    """Download the raw HTML data from a Google Doc."""
    service = authenticate("docs", "v1")
    document_id = re.search("(?<=/d/)(.*?)(?=/)", url).group()
    document = service.documents().get(documentId=document_id).execute()
    body = document.get('body')

    html = ""

    for block in body.get('content'):
        # Skip line if not a paragraph
        if 'paragraph' not in block.keys():
            continue

        paragraph_body = ""

        for element in block.get('paragraph').get('elements'):
            text_run = element.get('textRun')

            if not text_run:
                continue

            opening_tag = ""
            closing_tag = ""

            if "bold" in text_run.get('textStyle').keys():
                opening_tag = "<strong>"
                closing_tag = "</strong>"

            if "italic" in text_run.get('textStyle').keys():
                opening_tag = "<em>"
                closing_tag = "</em>"

            if "link" in text_run.get('textStyle').keys():
                opening_tag = f" <a href='{text_run.get('textStyle').get('link').get('url')}'>"
                closing_tag = "</a> "

            content = text_run.get('content').strip()

            if not content:
                continue

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

    output_file = Path("tmp", metadata.get('name'))

    with open(output_file, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while done is False:
            _, done = downloader.next_chunk()

    return output_file
