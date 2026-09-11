"""Notification delivery, also retried."""

import time


def send(client, address, body):
    """Retry is safe here: the provider dedupes on message id."""
    for _ in range(3):
        try:
            return client.send(address, body, message_id=body["id"])
        except TimeoutError:
            time.sleep(1)
    raise TimeoutError(address)
