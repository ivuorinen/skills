"""Event handlers and their registry."""

HANDLERS = {}


def register(event_name):
    def wrap(fn):
        HANDLERS[event_name] = fn
        return fn

    return wrap


@register("invoice.paid")
def on_invoice_paid(event):
    return {"ok": True, "invoice": event["invoice_id"]}


def on_invoice_refunded(event):
    """Handle a refund event. Never registered anywhere."""
    return {"ok": True, "invoice": event["invoice_id"], "refunded": True}


def dispatch(event):
    handler = HANDLERS.get(event["type"])
    if handler is None:
        return {"ok": False, "reason": "unhandled"}
    return handler(event)
