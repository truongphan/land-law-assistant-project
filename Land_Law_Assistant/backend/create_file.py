# save_real_pdf.py
import requests

url = "https://thads.moj.gov.vn/binhdinh/noidung/thongbao/Lists/ThongBao/Attachments/422/Lu%E1%BA%ADt-31-2024-QH15.pdf"

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

print("Đang tải file thật...")
response = requests.get(url, headers=headers)

if response.status_code == 200:
    with open("Luat_Dat_Dai_Real.pdf", "wb") as f:
        f.write(response.content)
    print(f"Tải thành công! Kích thước: {len(response.content)/1024:.2f} KB")
else:
    print(f"Lỗi tải file: {response.status_code}")