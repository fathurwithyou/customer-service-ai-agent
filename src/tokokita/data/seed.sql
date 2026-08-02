-- seed.sql -- dummy data covering the scenarios the assistant is meant to handle.
--
-- Orders 1-3 are fixed: the tests assert on them. Everything from 4 up exists so a demo can
-- reach a case that 1-3 cannot -- an address that CAN still be changed, a refund over the
-- ceiling, an unpaid order, a cancellation, and a delivery the customer says never arrived.
--
-- Dates are relative so the history reads sensibly instead of every order landing in the same
-- second.

INSERT INTO customers (full_name, email, phone, loyalty_tier) VALUES
 ('Andi Wijaya',   'andi@example.com',  '081200000001', 'gold'),
 ('Bunga Lestari', 'bunga@example.com', '081200000002', 'silver'),
 ('Citra Dewi',    'citra@example.com', '081200000003', 'bronze');   -- no orders yet

INSERT INTO products (name, category, price, stock_qty, description) VALUES
 ('Kaos Polos Hitam',  'Fashion',    89000,  120, 'Kaos katun combed 30s, unisex.'),
 ('Sepatu Sneakers',   'Fashion',   349000,  15,  'Sneakers kasual putih.'),
 ('Botol Minum 1L',    'Rumah',      65000,  0,   'Botol tritan bebas BPA.'),   -- out of stock
 ('Jam Tangan Kulit',  'Aksesoris', 1250000, 4,   'Jam tangan tali kulit asli, tahan air 5ATM.'),
 ('Tas Ransel Kanvas', 'Fashion',   275000,  38,  'Ransel kanvas 20L, muat laptop 14 inci.'),
 ('Lampu Meja LED',    'Rumah',     135000,  62,  'Lampu meja LED, 3 tingkat kecerahan.');

INSERT INTO orders (customer_id, order_date, status, total_amount, shipping_address, payment_method) VALUES
 (1, now() - interval '6 days',  'shipped',    178000,  'Jl. Melati No. 1, Jakarta',  'va_bca'),
 (1, now() - interval '9 days',  'delivered',  349000,  'Jl. Melati No. 1, Jakarta',  'gopay'),
 (2, now() - interval '2 days',  'processing', 65000,   'Jl. Kenanga No. 9, Bandung', 'cod'),
 -- Andi, still editable: the only way to demonstrate a successful address change.
 (1, now() - interval '1 days',  'processing', 410000,  'Jl. Melati No. 1, Jakarta',  'va_bca'),
 -- Andi, above the Rp 1.000.000 refund ceiling.
 (1, now() - interval '14 days', 'delivered',  2500000, 'Jl. Melati No. 1, Jakarta',  'credit_card'),
 -- Andi, awaiting payment: "kenapa pesanan saya belum diproses?"
 (1, now() - interval '3 hours', 'pending',    135000,  'Jl. Melati No. 1, Jakarta',  'va_bca'),
 -- Andi, cancelled: address change refused for a different reason than "already shipped".
 (1, now() - interval '20 days', 'cancelled',  89000,   'Jl. Melati No. 1, Jakarta',  'ovo'),
 -- Bunga, marked delivered but the parcel never arrived: the record contradicts the customer.
 (2, now() - interval '11 days', 'delivered',  275000,  'Jl. Kenanga No. 9, Bandung', 'gopay');

INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
 (1, 1, 2, 89000),
 (2, 2, 1, 349000),
 (3, 3, 1, 65000),
 (4, 5, 1, 275000),
 (4, 6, 1, 135000),        -- two items, so a return has to name which product
 (5, 4, 2, 1250000),       -- Rp 2.500.000, over the ceiling
 (6, 6, 1, 135000),
 (7, 1, 1, 89000),
 (8, 5, 1, 275000);

INSERT INTO shipments (order_id, courier, tracking_number, status, estimated_delivery, shipped_at, delivered_at) VALUES
 (1, 'JNE',      'JNE0012345678', 'in_transit',       (now() + interval '1 days')::date,  now() - interval '5 days',  NULL),
 (2, 'SiCepat',  'SIC0098765432', 'delivered',        (now() - interval '7 days')::date,  now() - interval '8 days',  now() - interval '7 days'),
 (5, 'AnterAja', 'AA0055512345',  'delivered',        (now() - interval '12 days')::date, now() - interval '13 days', now() - interval '12 days'),
 (7, 'JNE',      'JNE0099887766', 'failed',           (now() - interval '18 days')::date, now() - interval '19 days', NULL),
 (8, 'J&T',      'JT0077123456',  'out_for_delivery', (now() - interval '9 days')::date,  now() - interval '10 days', NULL);

INSERT INTO payments (order_id, amount, method, status, paid_at) VALUES
 (1, 178000,  'va_bca',      'paid',     now() - interval '6 days'),
 (2, 349000,  'gopay',       'paid',     now() - interval '9 days'),
 (3, 65000,   'cod',         'pending',  NULL),
 (4, 410000,  'va_bca',      'paid',     now() - interval '1 days'),
 (5, 2500000, 'credit_card', 'paid',     now() - interval '14 days'),
 (6, 135000,  'va_bca',      'pending',  NULL),     -- unpaid, so the order sits at 'pending'
 (7, 89000,   'ovo',         'refunded', now() - interval '19 days'),
 (8, 275000,  'gopay',       'paid',     now() - interval '11 days');

-- An earlier return, so return history is not empty on a fresh database.
INSERT INTO returns (order_id, product_id, reason, status, refund_amount, requested_at) VALUES
 (2, 2, 'Ukuran kekecilan', 'completed', 349000, now() - interval '6 days');

INSERT INTO tickets (customer_id, order_id, category, priority, status, subject, created_at) VALUES
 (1, 1, 'shipping', 'medium', 'open',      'Pesanan belum sampai', now() - interval '2 days'),
 (2, 8, 'shipping', 'high',   'escalated', 'Paket tertulis terkirim tapi belum diterima',
  now() - interval '1 days');

INSERT INTO ticket_messages (ticket_id, sender, message, created_at) VALUES
 (1, 'customer', 'Halo, pesanan order 1 saya kok belum sampai ya?', now() - interval '2 days'),
 (2, 'customer', 'Statusnya terkirim tapi barangnya tidak ada di rumah saya.', now() - interval '1 days');
