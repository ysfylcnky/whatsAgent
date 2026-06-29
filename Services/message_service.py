import time

from config import PROCESSED_MESSAGE_TTL

processed_messages = {}


def is_duplicate(message_id):

    now = time.time()

    expired = [
        mid
        for mid, created_at in processed_messages.items()
        if now - created_at > PROCESSED_MESSAGE_TTL
    ]

    for mid in expired:
        del processed_messages[mid]

    if message_id in processed_messages:
        return True

    processed_messages[message_id] = now

    return False