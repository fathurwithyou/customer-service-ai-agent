-- schema.sql  (SQLite -- dummy/local dev)
PRAGMA foreign_keys = ON;

CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT NOT NULL,
    email         TEXT UNIQUE NOT NULL,
    phone         TEXT,
    loyalty_tier  TEXT DEFAULT 'bronze',            -- bronze / silver / gold
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE products (
    product_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    category    TEXT,
    price       REAL NOT NULL,
    stock_qty   INTEGER DEFAULT 0,
    description TEXT
);

CREATE TABLE orders (
    order_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id      INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date       TEXT DEFAULT (datetime('now')),
    status           TEXT NOT NULL,                 -- pending/paid/processing/shipped/delivered/cancelled
    total_amount     REAL,
    shipping_address TEXT,
    payment_method   TEXT
);

CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id      INTEGER NOT NULL REFERENCES orders(order_id),
    product_id    INTEGER NOT NULL REFERENCES products(product_id),
    quantity      INTEGER NOT NULL,
    unit_price    REAL NOT NULL
);

CREATE TABLE shipments (
    shipment_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id           INTEGER NOT NULL REFERENCES orders(order_id),
    courier            TEXT,                         -- JNE / J&T / SiCepat / AnterAja
    tracking_number    TEXT,
    status             TEXT,                         -- picked_up/in_transit/out_for_delivery/delivered/failed
    estimated_delivery TEXT,
    shipped_at         TEXT,
    delivered_at       TEXT
);

CREATE TABLE payments (
    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL REFERENCES orders(order_id),
    amount     REAL,
    method     TEXT,                                -- va_bca/gopay/ovo/cod/credit_card
    status     TEXT,                                -- pending/paid/failed/refunded
    paid_at    TEXT
);

CREATE TABLE returns (
    return_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id      INTEGER NOT NULL REFERENCES orders(order_id),
    product_id    INTEGER NOT NULL REFERENCES products(product_id),
    reason        TEXT,
    status        TEXT DEFAULT 'requested',         -- requested/approved/rejected/completed
    refund_amount REAL,
    requested_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE tickets (
    ticket_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    order_id    INTEGER REFERENCES orders(order_id),
    category    TEXT,                                -- shipping/refund/product/payment/other
    priority    TEXT,                                -- low/medium/high/urgent
    status      TEXT DEFAULT 'open',                 -- open/pending/resolved/escalated
    subject     TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    resolved_at TEXT
);

CREATE TABLE ticket_messages (
    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id  INTEGER NOT NULL REFERENCES tickets(ticket_id),
    sender     TEXT,                                -- customer/agent/ai
    message    TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- One row per ModelMessage. The columns are the fields pydantic-ai puts on every message;
-- the message itself stays in `payload` in the framework's own format, so a new part type
-- needs no migration.
CREATE TABLE conversation_messages (
    message_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,                  -- ModelMessage.conversation_id
    seq         INTEGER NOT NULL,               -- order within the conversation
    kind        TEXT NOT NULL,                  -- ModelMessage.kind: request | response
    run_id      TEXT,                           -- groups the messages of one agent run
    created_at  TEXT,                           -- ModelMessage.timestamp; null on a request
    payload     TEXT NOT NULL,
    UNIQUE (session_id, seq)
);
