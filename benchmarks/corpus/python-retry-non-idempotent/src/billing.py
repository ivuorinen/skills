"""Billing operations."""

import time


class Gateway:
    def charge(self, account, cents, idempotency_key=None):
        """Charge an account. Duplicate-safe only when given a key."""
        raise NotImplementedError


def fetch_balance(gateway, account):
    """Safe to retry: a read."""
    for _ in range(3):
        try:
            return gateway.balance(account)
        except TimeoutError:
            time.sleep(1)
    raise TimeoutError(account)


def charge_with_retry(gateway, account, cents):
    """Charge, retrying on timeout."""
    for _ in range(3):
        try:
            return gateway.charge(account, cents)
        except TimeoutError:
            time.sleep(1)
    raise TimeoutError(account)
