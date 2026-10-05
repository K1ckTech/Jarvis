import urllib.request
import json
import sys

req = urllib.request.Request(
    "http://localhost:8000/api/chat",
    data=json.dumps({"message":"hello", "provider":"openai", "model":"llama3.1", "base_url":"http://localhost:11434/v1", "thread_id":"test"}).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)
try:
    with urllib.request.urlopen(req) as f:
        while True:
            chunk = f.read(1024)
            if not chunk:
                break
            sys.stdout.write(chunk.decode("utf-8"))
except Exception as e:
    print("Error:", e)
