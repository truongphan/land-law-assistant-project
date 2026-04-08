import time
from pinecone import Pinecone, ServerlessSpec

PINECONE_API_KEY = "pcsk_*"

OLD_INDEX_NAME = "hackathon-fpt-final"
NEW_INDEX_NAME = "land-law-assistant"
DIMENSION = 1024

def reset_index():
    pc = Pinecone(api_key=PINECONE_API_KEY)
    
    existing_indexes = [i.name for i in pc.list_indexes()]
    print(f"Danh sách Index hiện tại: {existing_indexes}")

    if OLD_INDEX_NAME in existing_indexes:
        print(f"Đang xóa index cũ: {OLD_INDEX_NAME} ...")
        pc.delete_index(OLD_INDEX_NAME)
        print("Đã xóa xong.")
    else:
        print(f"Index {OLD_INDEX_NAME} không tồn tại.")

    if NEW_INDEX_NAME not in existing_indexes:
        print(f"Đang tạo index mới: {NEW_INDEX_NAME} (Dim={DIMENSION})...")
        try:
            pc.create_index(
                name=NEW_INDEX_NAME,
                dimension=DIMENSION, 
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
            print(f"Tạo thành công index: {NEW_INDEX_NAME}")
        except Exception as e:
            print(f"Lỗi khi tạo index (có thể do trùng tên hoặc limit): {e}")
    else:
        print(f"Index {NEW_INDEX_NAME} đã tồn tại. Bỏ qua tạo mới.")

    print("\nKiểm tra trạng thái Index mới:")
    while not pc.describe_index(NEW_INDEX_NAME).status['ready']:
        time.sleep(1)
    print("Index đã SẴN SÀNG hoạt động!")

if __name__ == "__main__":
    reset_index()