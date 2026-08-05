Nạp các thư viện cần thiết

```python
from pathlib import Path 
import hashlib 

import pandas as pd
```

Đọc file cần thiết

```python
WORKING_PATH = Path().resolve().parent
DATA_PATH = WORKING_PATH / "data" / "data.csv"
CHUNK_SIZE=250_000
EXPECTED_COLUMNS = [
    "step", "type", "amount", "nameOrig", "oldbalanceOrg", "newbalanceOrig",
    "nameDest", "oldbalanceDest", "newbalanceDest", "isFraud", "isFlaggedFraud",
]
with DATA_PATH.open("rb") as file:
    csv_sha256 = hashlib.file_digest(file,"sha256").hexdigest() 


```

EDA

```python
import pandas as pd

# 1. Khai báo tập hợp kiểm tra (Dùng set {} để tra cứu nhanh hơn list [])
valid_types = {"CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"}
valid_fraud = {0, 1}

stats = {
    "min_step": float("inf"), "max_step": float("-inf"),
    "min_amount": float("inf"), "max_amount": float("-inf"),
    "min_old_balance_org": float("inf"), "max_old_balance_org": float("-inf"),
    "min_new_balance_orig": float("inf"), "max_new_balance_orig": float("-inf"),
    "min_old_balance_dest": float("inf"), "max_old_balance_dest": float("-inf"),
    "min_new_balance_dest": float("inf"), "max_new_balance_dest": float("-inf"),
    "duplicate_rows": 0 , 
}

seen_types = set()
seen_hashes = set()
seen_fraud = set()
seen_flagged_fraud =set()

null_per_columns = None
total_rows = 0
#Vòng lặp xử lý từng chunk
for chunk in pd.read_csv(DATA_PATH, chunksize=CHUNK_SIZE):

    total_rows += len(chunk)

    chunk_null = chunk.isnull().sum()
    if null_per_columns is None:
        null_per_columns = chunk_null
    else:
        null_per_columns += chunk_null
        
    stats["min_step"] = min(stats["min_step"], chunk["step"].min())
    stats["max_step"] = max(stats["max_step"], chunk["step"].max())

    stats["min_amount"] = min(stats["min_amount"], chunk["amount"].min())
    stats["max_amount"] = max(stats["max_amount"], chunk["amount"].max())

    stats["min_old_balance_org"] = min(stats["min_old_balance_org"], chunk["oldbalanceOrg"].min())
    stats["max_old_balance_org"] = max(stats["max_old_balance_org"], chunk["oldbalanceOrg"].max())

    stats["min_new_balance_orig"] = min(stats["min_new_balance_orig"], chunk["newbalanceOrig"].min())
    stats["max_new_balance_orig"] = max(stats["max_new_balance_orig"], chunk["newbalanceOrig"].max())

    stats["min_old_balance_dest"] = min(stats["min_old_balance_dest"], chunk["oldbalanceDest"].min())
    stats["max_old_balance_dest"] = max(stats["max_old_balance_dest"], chunk["oldbalanceDest"].max())

    stats["min_new_balance_dest"] = min(stats["min_new_balance_dest"], chunk["newbalanceDest"].min())
    stats["max_new_balance_dest"] = max(stats["max_new_balance_dest"], chunk["newbalanceDest"].max())

        
    # --- TÌM BẢN GHI TRÙNG LẶP 100% (EXACT DUPLICATE) ---
    chunk_hashes = pd.util.hash_pandas_object(chunk, index=False)
    for h in chunk_hashes:
        if h in seen_hashes:
            stats["duplicate_rows"] += 1
        else:
            seen_hashes.add(h)
    seen_types.update(chunk["type"].unique())
    seen_fraud.update(chunk["isFraud"].unique())
    seen_flagged_fraud.update(chunk["isFlaggedFraud"].unique())

columns = pd.read_csv(DATA_PATH,nrows=0).columns.to_list()
len_columns = len(columns)
# --- IN KẾT QUẢ ĐỂ XÁC ĐỊNH WORKFLOW & WRITE RULES FOR DBT ---
print("=== KẾT QUẢ THỐNG KÊ (STATS) ===")
for k, v in stats.items():
    print(f"{k}: {v}")
for _ in [seen_fraud,seen_flagged_fraud,seen_types]:
    print(_)
print("Số cột là: ",len_columns)
print("Tên các cột là: ",columns) 
print("Số lượng null của từng cột là:\n",null_per_columns)
print("Các cột chứa giá trị null là:\n",null_per_columns[null_per_columns>0])
print("% Số lượng null của từng cột là:\n", (null_per_columns/total_rows *100).round(2).astype(str) + '%')

```

Dựa vào đây ta thấy dữ liệu được chuẩn hóa khá sạch

```python

```