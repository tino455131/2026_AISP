# demo_data — 假的 bot 資料庫（測試用）

用 `Demo_Script.md` 產生一個和真的 bot 資料庫同樣結構的假資料庫，讓 AI 組在自己電腦上測試，不用碰真的錄音和訊息。

| 檔案 | 做什麼 |
|---|---|
| `make_demo_db.py` | 產生假資料庫，放在 `demo_data/out/`（不進 git） |
| `fake_access.py` | 不用連 Discord 的權限判斷，可以自己設定誰看得到哪個頻道 |
| `try_readers.py` | 示範怎麼透過讀取介面拿資料，以及被拒絕時會怎樣 |
| `test_demo_data.py` | 確認假資料庫和真的程式接得起來 |

怎麼用、每個函式拿到什麼，見 [docs/ai_team_guide.md](../docs/ai_team_guide.md)。
