import json
import urllib.request

url = "http://127.0.0.1:8000/debug/transcript-correction"

data = {
    "language": "zh",
    "segments": [
        {
            "id": 0,
            "text": "水泥的售命只有50年"
        },
        {
            "id": 1,
            "text": "这完全就是两马事儿啊"
        },
        {
            "id": 2,
            "text": "工程师会在房子的横量楼板"
        }
    ]
}

body = json.dumps(
    data,
    ensure_ascii=False
).encode("utf-8")

request = urllib.request.Request(
    url,
    data=body,
    headers={
        "Content-Type": "application/json; charset=utf-8"
    },
    method="POST"
)

with urllib.request.urlopen(request) as response:
    result = json.loads(response.read().decode("utf-8"))

print("=== RAW ===")
for item in result.get("raw", []):
    print(item)

print("\n=== CORRECTED ===")
for item in result.get("corrected", []):
    print(
        f'{item["id"]}: {item["corrected_text"]}'
    )

print("\n=== STATUS ===")
for key in [
    "enabled",
    "attempted",
    "success",
    "fallback",
    "changed_segments",
    "total_segments",
    "batches",
    "failed_batches",
    "zero_change_warning",
    "error",
]:
    print(f"{key}: {result.get(key)}")

with open(
    "correction-result-utf8.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(result, f, ensure_ascii=False, indent=2)