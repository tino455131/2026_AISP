"""ai_demo — 【測試用】讀本機 SQLite，照 spec 做會議之後的 AI 功能。

這是 AI 組正式版出來前的示範與測試，不是正式功能：
- 直接讀資料庫，不檢查 Discord 權限（正式版必須經過 AuthorizedTranscriptReader 等讀取介面，spec R15）
- 結果只印在終端機，不發到 Discord
- AI 預設用這台電腦的 Claude Code（和摘要一樣），可以換成 claude、openai 或自訂來源
"""
