# Product Requirements Document — Asisten Customer Service TokoKita

| | |
|---|---|
| **Produk** | Asisten Customer Service (chat) untuk TokoKita |
| **Versi** | 1.0 (draft) |
| **Tanggal** | 2 Agustus 2026 |
| **Status** | Menunggu review tim teknis |
| **Pemilik** | Saya, pemilik TokoKita |

---

## 1. Ringkasan

Saya menjalankan toko online TokoKita. Saya ingin punya asisten chat yang bisa melayani pelanggan saya sepanjang waktu — menjawab pertanyaan umum, membantu urusan pesanan dan retur, dan tahu kapan harus memanggil petugas manusia. Yang saya kejar sederhana: pelanggan saya dilayani cepat dan ramah kapan pun, dan tim saya tidak lagi kewalahan menjawab pertanyaan yang itu-itu saja.

Dokumen ini menjelaskan apa yang saya butuhkan dan seperti apa keberhasilannya. Cara membangunnya saya serahkan ke tim teknis.

---

## 2. Latar Belakang & Masalah

Setiap hari pelanggan saya menghubungi kami untuk hal yang mirip: "pesanan saya sampai mana?", "barangnya masih ada?", "cara retur bagaimana?". Masalahnya:

- Balasan sering lambat, terutama di malam hari dan akhir pekan.
- Tim CS saya habis waktu untuk pertanyaan berulang, jadi keluhan yang lebih penting jadi tertunda.
- Pelanggan kesal karena harus menunggu dan sering mengulang cerita dari awal.

Kalau ini dibiarkan, pelanggan kabur ke toko lain dan reputasi saya turun.

---

## 3. Tujuan & Ukuran Keberhasilan

Saya menganggap produk ini berhasil kalau:

- Pelanggan mendapat balasan **dalam hitungan detik**, kapan pun mereka chat.
- **Sebagian besar pertanyaan (target sekitar 6 dari 10)** selesai tanpa perlu petugas manusia.
- **Penilaian kepuasan pelanggan naik** (target rata-rata minimal 4,2 dari 5).
- **Keluhan "lama dibalas" turun drastis.**
- Tim CS saya bisa fokus ke kasus yang benar-benar butuh manusia.

---

## 4. Siapa Penggunanya

- **Pelanggan toko** — orang yang belanja di TokoKita dan chat untuk bertanya atau minta bantuan. Mereka tidak mau ribet; mereka mau jawaban cepat dan jelas.
- **Tim CS saya** — menerima kasus yang dilempar asisten, dan sesekali mengecek apakah asisten bekerja dengan benar.

---

## 5. Cerita Pengguna

- Sebagai pelanggan, saya ingin tahu posisi paket dan perkiraan tibanya, supaya saya tenang menunggu.
- Sebagai pelanggan, saya ingin mengajukan retur atau pengembalian dana dengan mudah, supaya saya tidak merasa dipersulit.
- Sebagai pelanggan, saya ingin tahu harga dan ketersediaan barang, supaya saya bisa segera memutuskan membeli.
- Sebagai pelanggan, saya ingin mengganti alamat pengiriman selama barang belum dikirim, supaya paket tidak salah tujuan.
- Sebagai pelanggan, saya ingin cepat disambungkan ke petugas manusia kalau masalah saya rumit, supaya tidak buntu.

---

## 6. Kebutuhan Fungsional

Ditulis dalam bahasa pelanggan, diberi prioritas **Wajib / Sebaiknya / Kalau bisa**.

| Yang harus bisa dilakukan asisten | Prioritas |
|---|---|
| Menjawab "pesanan saya sampai mana?" dengan posisi paket & perkiraan tiba | Wajib |
| Membantu mengajukan retur / pengembalian dana sesuai aturan toko | Wajib |
| Menjawab harga, stok, dan info produk | Wajib |
| Menyambungkan ke petugas manusia saat asisten tidak bisa menangani | Wajib |
| Memastikan dulu bahwa penanya benar pemilik pesanan sebelum memberi detail | Wajib |
| Mengganti alamat pengiriman selama pesanan belum dikirim | Sebaiknya |
| Mengingat isi percakapan supaya pelanggan tidak mengulang | Sebaiknya |
| Memberi rekomendasi produk yang relevan | Kalau bisa |

---

## 7. Kebutuhan Non-Fungsional (Kualitas)

- **Cepat** — jawaban muncul dalam beberapa detik.
- **Ramah & jelas** — memakai Bahasa Indonesia yang sopan dan mudah dipahami, tidak kaku seperti robot.
- **Aman** — data pesanan dan data pribadi pelanggan tidak boleh bocor atau tertukar antar pelanggan.
- **Bisa diandalkan** — tetap melayani meski banyak pelanggan chat bersamaan.
- **Bisa dipertanggungjawabkan** — tindakan penting seperti retur dan ganti alamat tercatat, supaya bisa saya periksa bila perlu.

---

## 8. Aturan & Batasan

1. **Tidak boleh mengarang.** Kalau tidak yakin, asisten mengaku tidak tahu dan menyambungkan ke petugas — bukan menebak soal pesanan, resi, atau harga.
2. **Wajib verifikasi dulu.** Sebelum memberi detail pesanan, pastikan penanya memang pemiliknya.
3. **Serahkan ke manusia untuk hal sensitif** — pengembalian dana bernilai besar, komplain serius, tuduhan penipuan, atau pelanggan yang marah dan minta bicara dengan orang.
4. **Jangan menjanjikan di luar kebijakan toko** — tidak ada ganti rugi atau diskon yang tidak saya izinkan.

---

## 9. Yang Tidak Termasuk (Untuk Sekarang)

- Melayani lewat telepon atau suara — cukup chat dulu.
- Bahasa selain Indonesia.
- Menangani urusan di luar toko saya (misalnya keluhan langsung ke kurir).
- Mengubah harga atau stok produk.

---

## 10. Asumsi & Ketergantungan

- Asisten boleh melihat data yang memang perlu: status pesanan, pengiriman, dan produk saya.
- Aturan retur/refund toko sudah jelas dan bisa diikuti asisten.
- Tim CS saya siap menerima kasus yang dilempar asisten.

---

## 11. Pertanyaan yang Masih Terbuka

- Berapa nilai pengembalian dana yang boleh diproses asisten sebelum wajib lewat manusia?
- Apakah pelanggan perlu login dulu, atau cukup menyebut nomor pesanan/email?
- Sampai berapa lama percakapan lama perlu diingat asisten?