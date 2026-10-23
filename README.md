<div align="center">
  <img src="icon.png" alt="Kitty for Mint" width="96" height="96">
  <h1>Kitty for Mint</h1>
  <p>Desktop pet mèo pixel-art cho Linux Mint — bản port từ <a href="https://github.com/wizenheimer/cupcake">Cupcake</a> (macOS).</p>
  <p>
    <a href="https://github.com/LeQuangHieu281206/kitty-for-mint">github.com/LeQuangHieu281206/kitty-for-mint</a>
  </p>
</div>

![Preview](docs/preview.png)

![Mèo ngủ trên giường](docs/sleep.png)

## Giới thiệu

Bản gốc Cupcake hiển thị mèo animation trên Dock của macOS. Linux không có Dock
kiểu đó, nên bản này biến mèo thành một **desktop pet**: cửa sổ trong suốt,
luôn nổi, kéo thả được, có menu chuột phải và tự nhớ vị trí.

- 18 nhân vật, 320 frame pixel-art.
- Animation `Chill`, `Wiggle`, các đòn đặc biệt và **Sleep** (ngủ).
- Click vào mèo để xem phản ứng nhảy/ăn; kéo thả để di chuyển.
- **Giường pixel-art** nằm ở đáy màn hình, ngay trên thanh dock/panel. Kéo ngang
  để đặt giường; click giường để gọi mèo lên ngủ hoặc đánh thức mèo.
- Mèo **tự đi lang thang** trên màn hình, thỉnh thoảng tự lên giường ngủ rồi
  thức dậy. Có thể tắt bằng mục `Roam Freely`.
- Thả mèo lên giường bằng chuột trái: mèo tự nằm vào đúng chỗ và ngủ.
- Tự lưu nhân vật, animation, vị trí mèo, vị trí giường và thiết lập lang thang
  vào `~/.config/cupcake/state.json`.
- Nhẹ: ~41–42.5 MB RAM, ~0.3% CPU khi idle/ngủ, ~1.1% khi đi bộ.

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

- **Click chuột trái vào mèo**: mèo nhảy (hoặc ăn với Zombie) một lần rồi trở
  lại trạng thái bình thường. Nếu mèo đang ngủ, click sẽ đánh thức mèo.
- **Chuột trái + kéo**: di chuyển mèo tự do. Thả gần giường, mèo sẽ tự nằm vào
  giường và ngủ.
- **Click giường**: gọi mèo lên giường ngủ; click lần nữa để đánh thức.
- **Kéo giường ngang**: dời giường dọc theo thanh dock/panel. Vị trí được lưu.
- **Chuột phải vào mèo hoặc giường**: chọn nhân vật, animation (gồm `Sleep`),
  `Go to Bed`/`Wake Up`, bật/tắt `Roam Freely`, random, About, Quit.
- **Roam Freely**: mặc định bật. Mèo tự đi đến vị trí ngẫu nhiên, thỉnh thoảng
  lên giường ngủ 30–90 giây rồi thức dậy. Tắt mục này nếu muốn mèo đứng yên.
- **Tray icon**: có trên Cinnamon/MATE/XFCE. Trên GNOME, tray icon bị bỏ qua vì
  GNOME không hiển thị tray kiểu cũ; dùng chuột phải vào mèo hoặc giường.

Bộ asset gốc không có frame ngủ riêng, nên `Sleep` dùng lại frame `Chill`
(chậm hơn) hoặc một frame của nhân vật đặc biệt, kèm chữ `Zzz` pixel vẽ bằng
cairo. Mèo vẫn nằm đúng trên giường và có thể ngủ ở mọi nhân vật.

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

Đo lại trên cấu hình ở trên, GNOME 46 Wayland qua XWayland (23/10/2026), có
giường và timer lang thang:

| Chỉ số | Kết quả |
|---|---|
| RAM (RSS) | ~41 MB khi idle/ngủ; tối đa ~42.5 MB sau khi đi bộ cả hai hướng |
| CPU (idle, animation chạy) | ~0.3% một core |
| CPU (ngủ, có Zzz) | ~0.3% một core |
| CPU (đi bộ, cửa sổ di chuyển 25 lần/giây) | ~1.1% một core |
| Khởi động | ~145 ms (import + mở hai cửa sổ) |
| Chuyển animation | 2–3 ms |
| File descriptor | 13, không tăng |
| Kiểm tra | 18 nhân vật / 320 frame; 3 test pass |

Phần lớn bộ nhớ là thư viện GTK3 (~38 MB). App chỉ cache frame của nhân vật
hiện tại (idle/jump/sleep, kể cả bản lật trái) thay vì cache toàn bộ 320 frame.
Giường là cửa sổ trong suốt nhỏ, vẽ bằng cairo, không thêm asset hay ảnh nền.
Frame ngủ dùng lại frame có sẵn nên không tăng dung lượng asset.

## Cấu trúc file

| File | Mô tả |
|---|---|
| `cupcake.py` | Toàn bộ app: cửa sổ mèo, giường, animation, di chuyển, menu, state |
| `install.sh` | Cài app vào `~/.local/share/cupcake` và tạo launcher |
| `test_cupcake.py` | Test load đủ frame, ID nhân vật và animation ngủ |
| `assets/` | 320 frame PNG 32×32 của 18 nhân vật |
| `icon.png` | Icon ứng dụng 256×256 |
| `docs/preview.png` | Preview các nhân vật |
| `docs/sleep.png` | Preview mèo ngủ trên giường |
| `LICENSE` | Giấy phép MIT |
| `.gitignore` | Bỏ qua `__pycache__`, `*.pyc` |

Chạy test:

```bash
python3 -m unittest test_cupcake.py -v
```

## Ghi chú Wayland

GTK3 không thể tự đặt vị trí hoặc giữ cửa sổ luôn nổi trên Wayland. Vì vậy app
tự đặt `GDK_BACKEND=x11` và cả mèo lẫn giường chạy qua **XWayland**; trên GNOME
Wayland đã kiểm tra vị trí, di chuyển cửa sổ và `_NET_WM_STATE_ABOVE` hoạt động.

Muốn thử native Wayland (vị trí và lớp cửa sổ do compositor quyết định):

```bash
GDK_BACKEND=wayland python3 cupcake.py
```

## Nguồn gốc và giấy phép

- Dự án gốc: [wizenheimer/cupcake](https://github.com/wizenheimer/cupcake) — MIT.
- Pixel-art assets lấy từ dự án gốc.
- Bản port Linux Mint: [LeQuangHieu281206](https://github.com/LeQuangHieu281206).

Phát hành theo giấy phép [MIT](LICENSE).
