<div align="center">
  <img src="icon.png" alt="Kitty for Mint" width="96" height="96">
  <h1>Kitty for Mint</h1>
  <p>Desktop pet mèo pixel-art cho Linux Mint — bản port từ <a href="https://github.com/wizenheimer/cupcake">Cupcake</a> (macOS).</p>
  <p>
    <a href="https://github.com/LeQuangHieu281206/kitty-for-mint">github.com/LeQuangHieu281206/kitty-for-mint</a>
  </p>
</div>

![Preview](docs/preview.png)

## Giới thiệu

Bản gốc Cupcake hiển thị mèo animation trên Dock của macOS. Linux không có Dock
kiểu đó, nên bản này biến mèo thành một **desktop pet**: cửa sổ trong suốt,
luôn nổi, kéo thả được, có menu chuột phải và tự nhớ vị trí.

- 18 nhân vật, 320 frame pixel-art.
- Animation `Chill`, `Wiggle` và các đòn đặc biệt.
- Kéo thả bằng chuột trái, menu bằng chuột phải.
- Chọn nhân vật, animation, random, About, Quit.
- Tự lưu nhân vật và vị trí vào `~/.config/cupcake/state.json`.
- Nhẹ: ~42 MB RAM, ~0.35% CPU khi chạy animation.

## Cấu hình máy đã kiểm thử

| Thành phần | Thông số |
|---|---|
| Máy | Dell Inspiron 15 3520 |
| Hệ điều hành | Linux Mint 22.3 “Zena” (nền Ubuntu 24.04 Noble) |
| Kernel | 7.0.0-38-generic, x86_64 |
| Desktop | GNOME 46.0, phiên **Wayland** (app chạy qua XWayland) |
| Màn hình | 1920 × 1080, 120 Hz |
| CPU | Intel Core i5-1135G7, 4 core / 8 thread, 2.4 GHz |
| RAM | 15 GiB khả dụng (16 GB) |
| Swap | 15 GiB: 7.6 GiB partition + 7.7 GiB zram |
| GPU | Intel Iris Xe (TigerLake-LP GT2) |
| Ổ cứng | NVMe: `/` 94 GB, `/home` 244 GB |
| Python | 3.12.3 |
| GTK | 3.24.41 |

Số liệu đo tại thời điểm kiểm tra: RAM đang dùng 12 GiB, còn 2.8 GiB khả dụng,
zram đang dùng 3.2 GiB. Bản thân app chỉ chiếm ~42 MB.

## Yêu cầu

- Linux Mint 21/22 hoặc Ubuntu/Debian có GTK3.
- Python 3.10+.
- Các gói:

```bash
sudo apt install -y python3-gi gir1.2-gtk-3.0 python3-gi-cairo
```

Linux Mint thường đã có sẵn cả ba gói.

## Cài đặt

```bash
git clone https://github.com/LeQuangHieu281206/kitty-for-mint.git
cd kitty-for-mint
./install.sh
cupcake
```

Lệnh cài sẽ:

1. Copy app vào `~/.local/share/cupcake`.
2. Tạo lệnh `cupcake` trong `~/.local/bin`.
3. Tạo mục **Cupcake** trong menu ứng dụng.

Nếu terminal báo không tìm thấy `cupcake`, thêm `~/.local/bin` vào `PATH` rồi
đăng nhập lại, hoặc chạy trực tiếp:

```bash
~/.local/bin/cupcake
```

Chạy không cần cài (dùng asset ngay trong repo):

```bash
python3 cupcake.py
```

## Sử dụng

- **Chuột trái + kéo**: di chuyển mèo.
- **Chuột phải vào mèo**: chọn nhân vật, animation, random, About, Quit.
- **Tray icon**: có trên Cinnamon/MATE/XFCE. Trên GNOME, tray icon bị bỏ qua vì
  GNOME không hiển thị tray kiểu cũ; dùng chuột phải vào mèo.

Tự khởi động cùng phiên đăng nhập:

```bash
mkdir -p ~/.config/autostart
cp ~/.local/share/applications/cupcake.desktop ~/.config/autostart/
```

Gỡ cài đặt:

```bash
rm -rf ~/.local/share/cupcake
rm -f ~/.local/bin/cupcake ~/.local/share/applications/cupcake.desktop
rm -f ~/.config/cupcake/state.json
```

## Hiệu năng

Đo trên cấu hình ở trên, GNOME 46 Wayland qua XWayland:

| Chỉ số | Kết quả |
|---|---|
| RAM (RSS) | ~41.6 MB, ổn định qua 60 giây |
| CPU | ~0.35% một core (21 tick / 60 giây) |
| Khởi động | ~116 ms (import 75 ms + mở cửa sổ 41 ms) |
| Chuyển animation | 2–3 ms |
| File descriptor | 13, không tăng |
| Kiểm tra | 18 nhân vật / 320 frame, tất cả load đúng |

Phần lớn bộ nhớ là thư viện GTK3 (~38 MB). App không cache toàn bộ 320 frame
để giữ RAM thấp; frame của nhân vật hiện tại được load khi cần.

## Cấu trúc file

| File | Mô tả |
|---|---|
| `cupcake.py` | Toàn bộ app: cửa sổ trong suốt, animation, menu, lưu trạng thái |
| `install.sh` | Cài app vào `~/.local/share/cupcake` và tạo launcher |
| `test_cupcake.py` | Test load đủ frame và ID nhân vật |
| `assets/` | 320 frame PNG 32×32 của 18 nhân vật |
| `icon.png` | Icon ứng dụng 256×256 |
| `docs/preview.png` | Ảnh preview cho README |
| `LICENSE` | Giấy phép MIT |
| `.gitignore` | Bỏ qua `__pycache__`, `*.pyc` |

Chạy test:

```bash
python3 -m unittest test_cupcake.py -v
```

## Ghi chú Wayland

GTK3 không thể tự đặt vị trí hoặc giữ cửa sổ luôn nổi trên Wayland. Vì vậy app
tự đặt `GDK_BACKEND=x11` và chạy qua **XWayland**; trên GNOME Wayland đã kiểm tra
vị trí và `_NET_WM_STATE_ABOVE` hoạt động.

Muốn thử native Wayland (vị trí và lớp cửa sổ do compositor quyết định):

```bash
GDK_BACKEND=wayland python3 cupcake.py
```

## Nguồn gốc và giấy phép

- Dự án gốc: [wizenheimer/cupcake](https://github.com/wizenheimer/cupcake) — MIT.
- Pixel-art assets lấy từ dự án gốc.
- Bản port Linux Mint: [LeQuangHieu281206](https://github.com/LeQuangHieu281206).

Phát hành theo giấy phép [MIT](LICENSE).
