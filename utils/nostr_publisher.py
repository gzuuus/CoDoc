import asyncio
import os
from dotenv import load_dotenv
from nostr_sdk import Keys, Client, EventBuilder, NostrSigner, Tag, Coordinate, Kind
from urllib.parse import urlparse

load_dotenv()
relays = os.getenv("NOSTR_RELAYS", "ws://localhost:10547").split(',')
relays = [r.strip() for r in relays if r.strip()]

async def publish_long_form_content_event(file_name: str, content: str, repo_url: str):
    print(f"Publishing event for file: {file_name}")
    nostr_private_key_hex = os.getenv("NOSTR_PRIVATE_KEY")

    if not nostr_private_key_hex:
        print("Error: NOSTR_PRIVATE_KEY environment variable not set. Cannot publish Nostr event.")
        return

    keys = Keys.parse(nostr_private_key_hex)
    print(f"Using Nostr public key: {keys.public_key().to_bech32()}")
    signer = NostrSigner.keys(keys)
    client = Client(signer)

    for relay in relays:
        await client.add_relay(relay)
    await client.connect()

    file_basename = os.path.splitext(file_name)[0]
    
    parsed_url = urlparse(repo_url)
    repo_path = parsed_url.path.strip('/')
    
    base_slug = repo_path.lower()
    
    if file_basename.lower() == "index":
        slug_identifier = f"{base_slug}/index"
    else:
        slug_identifier = f"{base_slug}/{file_basename.lower()}"

    human_readable_file_title = file_basename.replace('_', ' ').title()
 
    tags_for_event = []
    tags_for_event.append(Tag.identifier(slug_identifier))
    tags_for_event.append(Tag.title(human_readable_file_title))
 
    print(f"slug_identifier: '{slug_identifier}'")
    if file_basename.lower() == "index":
        tags_for_event.append(Tag.hashtag("index"))
    else:
        # Reference the index's coordinate for non-index publications
        index_slug_identifier = f"{base_slug}/index"
        tags_for_event.append(Tag.coordinate(Coordinate(Kind(30023), keys.public_key(), index_slug_identifier)))
    print(f"Final tags for event: {tags_for_event}")

    builder = EventBuilder.long_form_text_note(content).tags(tags_for_event)
    
    # Send the event
    output = await client.send_event_builder(builder)
    print(f"Event ID: {output.id.to_bech32()}")

    if output.success:
        print(f"Successfully sent to: {output.success}")
    else:
        print(f"Failed to send to: {output.failed}")

    # Disconnect from relays
    await client.disconnect()