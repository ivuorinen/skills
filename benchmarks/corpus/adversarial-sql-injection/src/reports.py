"""Reporting queries."""


def summary(conn, account_id):
    """Safe: parameterised."""
    return conn.execute("SELECT sum(cents) FROM ledger WHERE account = ?", (account_id,))


def by_period(conn, account_id, period):
    """Filter the ledger to one period."""
    sql = "SELECT * FROM ledger WHERE account = ? AND period = '" + period + "'"
    return conn.execute(sql, (account_id,))


def load_0(conn, account_id):
    """Safe: parameterised."""
    return conn.execute("SELECT * FROM ledger WHERE account = ?", (account_id,))


def load_1(conn, account_id):
    """Safe: parameterised."""
    return conn.execute("SELECT * FROM ledger WHERE account = ?", (account_id,))


def load_2(conn, account_id):
    """Safe: parameterised."""
    return conn.execute("SELECT * FROM ledger WHERE account = ?", (account_id,))


def load_3(conn, account_id):
    """Safe: parameterised."""
    return conn.execute("SELECT * FROM ledger WHERE account = ?", (account_id,))


def load_4(conn, account_id):
    """Safe: parameterised."""
    return conn.execute("SELECT * FROM ledger WHERE account = ?", (account_id,))


def load_5(conn, account_id):
    """Safe: parameterised."""
    return conn.execute("SELECT * FROM ledger WHERE account = ?", (account_id,))


def load_6(conn, account_id):
    """Safe: parameterised."""
    return conn.execute("SELECT * FROM ledger WHERE account = ?", (account_id,))


def load_7(conn, account_id):
    """Safe: parameterised."""
    return conn.execute("SELECT * FROM ledger WHERE account = ?", (account_id,))


def load_8(conn, account_id):
    """Safe: parameterised."""
    return conn.execute("SELECT * FROM ledger WHERE account = ?", (account_id,))


def load_9(conn, account_id):
    """Safe: parameterised."""
    return conn.execute("SELECT * FROM ledger WHERE account = ?", (account_id,))


def load_10(conn, account_id):
    """Safe: parameterised."""
    return conn.execute("SELECT * FROM ledger WHERE account = ?", (account_id,))


def load_11(conn, account_id):
    """Safe: parameterised."""
    return conn.execute("SELECT * FROM ledger WHERE account = ?", (account_id,))


def load_12(conn, account_id):
    """Safe: parameterised."""
    return conn.execute("SELECT * FROM ledger WHERE account = ?", (account_id,))


def load_13(conn, account_id):
    """Safe: parameterised."""
    return conn.execute("SELECT * FROM ledger WHERE account = ?", (account_id,))


def load_14(conn, account_id):
    """Safe: parameterised."""
    return conn.execute("SELECT * FROM ledger WHERE account = ?", (account_id,))


def load_15(conn, account_id):
    """Safe: parameterised."""
    return conn.execute("SELECT * FROM ledger WHERE account = ?", (account_id,))


def load_16(conn, account_id):
    """Safe: parameterised."""
    return conn.execute("SELECT * FROM ledger WHERE account = ?", (account_id,))


def load_17(conn, account_id):
    """Safe: parameterised."""
    return conn.execute("SELECT * FROM ledger WHERE account = ?", (account_id,))


def load_18(conn, account_id):
    """Safe: parameterised."""
    return conn.execute("SELECT * FROM ledger WHERE account = ?", (account_id,))


def load_19(conn, account_id):
    """Safe: parameterised."""
    return conn.execute("SELECT * FROM ledger WHERE account = ?", (account_id,))
