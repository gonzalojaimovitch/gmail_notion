import os
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from notion_client import Client
import datetime
import math
import json
import re
import base64
import email
import tqdm

with open(os.path.join(os.path.dirname(__file__), "config.json"), "r") as file:
    config = json.load(file)


# Initialize the Gmail API
def gmail_service():
    # Load credentials and create a service
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        "credentials.json", scopes=["https://www.googleapis.com/auth/gmail.readonly"]
    )
    credentials = flow.run_local_server()
    service = googleapiclient.discovery.build("gmail", "v1", credentials=credentials)
    return service


# Function to search Gmail for emails with a specific label
def search_emails(service, label_id, start_timestamp, end_timestamp):
    # Call the Gmail API
    results = (
        service.users()
        .messages()
        .list(
            userId="me",
            labelIds=[label_id],
            q=f"after:{start_timestamp} before:{end_timestamp}",
            maxResults=500,
        )
        .execute()
    )
    messages = results.get("messages", [])
    return messages


# Function to get an email content
def get_message(service, id):
    # Call the Gmail API
    raw_message = (
        service.users().messages().get(userId="me", id=id, format="raw").execute()
    )
    message = service.users().messages().get(userId="me", id=id).execute()
    message["raw"] = raw_message["raw"]
    return message


# Initialize Notion Client
def notion_client(token):
    return Client(auth=token)


# Function to create a page in Notion
def create_notion_page(notion, database_id, email_subject, url):
    new_page = notion.pages.create(
        parent={"database_id": database_id},
        properties={
            "Name": {"title": [{"text": {"content": email_subject}}]},
            "URL": {"url": url},
        },
    )
    return new_page


# Main function
def main():
    # Initialize services
    gmail = gmail_service()
    notion = notion_client(os.getenv("notion_api_key"))

    # Define your Gmail label and Notion database ID
    gmail_label = config["gmail_label"]
    notion_database_id = config["notion_database_id"]

    # Search for emails with the label and time
    start_timestamp = config["last_update_seconds"]
    end_timestamp = math.floor(datetime.datetime.now(datetime.timezone.utc).timestamp())
    mails = search_emails(
        gmail, gmail_label, start_timestamp=start_timestamp, end_timestamp=end_timestamp
    )

    # Add entries for each email retrieved
    if len(mails) == 0:
        print("No new entries found")
    else:
        for mail in tqdm.tqdm(mails):
            message = get_message(gmail, mail["id"])
            mime_msg = email.message_from_bytes(
                base64.urlsafe_b64decode(message["raw"]), policy=email.policy.default
            )
            # Get subject
            subject = ""
            for header in message["payload"]["headers"]:
                if header["name"] == "Subject":
                    subject = header["value"]
                    break
            # Get url
            mail_text = str(
                mime_msg.get_body(preferencelist=("plain", "related", "html"))
            )
            urls = re.findall("(?P<url>https?://[^\s]+)", mail_text)
            url = urls[-1] if urls else None
            # Create a new page in Notion for each email
            create_notion_page(
                notion, notion_database_id, email_subject=subject, url=url
            )
        print(f"{len(mails)} entries uploaded to Notion successfully")

    with open(os.path.join(os.path.dirname(__file__), "config.json"), "w") as file:
        config["last_update_seconds"] = end_timestamp
        json.dump(config, file)


if __name__ == "__main__":
    main()
