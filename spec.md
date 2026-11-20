# Discord Team AI 功能與系統 spec

版本：v1.1｜2026-11-20｜範圍：英文識別名稱修訂｜狀態：`implementation_paused`



## 目的與範圍

協助 `TeamLeader` 將文字會議決議落實為任務，依 `TeamLeader` 設定詢問 `TaskOwner` 進度、提醒待辦，並將有依據的進度與風險回報 `TeamLeader`。主要驗收流程是「文字會議 → 正式任務 → 提醒／詢問 → `TeamMember` 回報 → `TeamLeader` 彙報」。

第一版使用一個 Discord server、一個 team、一位設定好的 `TeamLeader`。所有資料與操作都帶有 `guild_id`、`team_id`，避免將來擴充多 team 時依賴全域單例。team 不等於頻道；同一 team 可以跨多個頻道，但資訊仍按來源隔離。

已確認的輸入是文字。Bot 可以查閱其有權限取得的頻道內容；這不代表每次對話都須呼叫 Claude，也不代表所有內容須永久複製進 database。語音轉錄、附件內容解析與跨 server 協作未列入本次已確認的功能。文字 thread 視為獨立來源，適用相同查詢及摘要規則；private thread 須額外判斷 membership，不能只沿用 parent channel 的可見判定。adapter 須按需取得可讀歷史，不能因 Gateway 未同步某個 archived thread 就把它判定為沒有對話。

## 技術命名規則

會成為 code／database 識別名稱的角色、資料類別、政策、欄位、事件與狀態使用英文。說明、使用者發言與實際顯示的訊息文案保留繁體中文。

| 用途 | 格式 | 範例 |
|---|---|---|
| 類別／資料型別／政策類別 | `PascalCase` | `Task`、`TaskOwner`、`SourceAccessPolicy` |
| 欄位／角色識別值／事件／狀態 | `snake_case` | `owner_user_id`、`team_leader`、`meeting_ended`、`awaiting_confirmation` |
| 錯誤代碼／Discord 原生權限 | `UPPER_SNAKE_CASE` | `ACCESS_DENIED_USER`、`VIEW_CHANNEL` |

類別名稱與識別值用來統一規格用語，不代表已建立同名 class、database table 或新的角色階層。既有英文欄位與 enum 值維持原名；API 平台替換另行討論。

## 角色與權責

| English name | 中文含義 | 識別值 | 可執行的業務行為 |
|---|---|---|---|
| `Administrator` | 管理者 | `administrator` | 明確設定 server 對應的 team 與 `TeamLeader`；身分由 Bot 的可信任設定介面驗證 |
| `TeamLeader` | 組長 | `team_leader` | 確認設定、開始／結束會議、正式分配或修改任務、取消／重開任務、確認代為轉達內容與對象 |
| `TeamMember` | 組員 | `team_member` | 依來源權限參與對話與查詢、提出建議；不因此取得正式指派或異動權限 |
| `TaskOwner` | 主要負責人／主責 | `task_owner` | 回報自己的任務進度、阻礙與完成狀態；確認允許分享的進度版本 |
| `Collaborator` | 協作者 | `collaborator` | 被列在任務中；不因此取得代 `TaskOwner` 正式回報的權限 |
| `AIAssistant` | AI 助理 | `ai_assistant` | 整理、抽取、追問、產生提案、依排程提醒與彙報；沒有自行提升資訊權限或修改 Discord 權限的權力 |
| `Scheduler` | 排程系統 | `scheduler` | 依已確認設定建立有限目的的工作，不視為擁有 `TeamLeader` 全部權限的使用者 |

`TaskOwner` 與 `Collaborator` 是相對於單項 `Task` 的關係，分別由 `owner_user_id` 與 `collaborators` 表達，不是對所有任務生效的全域角色。同一人可以同時是 `TeamLeader` 與某項任務的 `TaskOwner`。`AIAssistant`、`Scheduler` 是系統 principal，不當成人類成員角色。正文中的 AI 指 `AIAssistant`。

`TeamLeader` 是應用程式業務身分，不會額外授予來源頻道讀取權。Discord role 名稱也不能取代有效頻道權限檢查。Discord 的角色與頻道 overwrites 共同影響權限。[Discord Permissions](https://docs.discord.com/developers/topics/permissions)

## 已確認的功能需求

| ID | 規則 | 
|---|---|
| R01 | 一個 server／team，保留多 team 擴充 | 
| R02 | Claude 使用 PTC，自訂工具由後端執行 | 
| R03 | 群聊只因 @Bot 或明確指令回答；`TeamLeader` 查詢以私訊為主 |
| R04 | 初始化詢問 `TeamLeader` 習慣，結構化設定經確認後啟用 |
| R05 | `TeamLeader` 開始／結束文字會議，結束後在原頻道發布紀錄 | 
| R06 | `TeamLeader` 明確指定工作、`TaskOwner` 與期限時自動建檔；歧義或缺漏先追問 | 
| R07 | 每項任務一位 `TaskOwner`，可列 `Collaborator` | 
| R08 | 五種正式狀態；逾期、未回覆另行標記 | 
| R09 | 設定決定提醒、追問、彙報週期與可發訊息時段 | 
| R10 | 提醒私訊 `TaskOwner`，進度／風險私訊有來源權限的 `TeamLeader`；私訊失敗記錄未送達 | 
| R11 | 進度以明確回報為準，不推定完成或編造百分比，風險附依據 | 
| R12 | 任務進度分享先告知；一般私聊不轉傳，混有私人資訊先確認分享版本 | Q
| R13 | 有成員新訊息的頻道每日在原處總結，時間由 `TeamLeader` 設定，Bot 訊息不觸發 | 
| R14 | 一般代為轉達先確認內容與對象，驗權後發送並標示來源是 `TeamLeader` | 
| R15 | 所有衍生資料沿用來源限制；`TeamLeader` 無例外；無權、Bot 無權及未找到需區分 | 
| R16 | channel 內跨來源回答先告知改用私訊，再驗權交付 | 
| R17 | 保存必要專案資料；原聊天編輯／刪除不自動改已成立任務 | 
| R18 | `TaskOwner` 無來源權限時先提醒 `TeamLeader`，等待決定，不改權限、不轉達、不啟動提醒 | 

## 事件與啟動條件

以下為本系統的事件識別名稱，不取代 Discord SDK 的原生 event 名稱。

| `trigger_kind` | 中文情境 | 行為 |
|---|---|---|
| `member_message` | 一般成員訊息 | 不自動代答；可記錄每日活動 watermark，或作為已啟動會議的輸入 |
| `bot_mentioned`／`command_invoked` | @Bot／明確指令 | 建立帶可信任身分的 query／command run |
| `direct_message_received` | 使用者私訊 Bot | 處理該人的查詢或任務回報；本版 server／team 由既定設定解析 |
| `meeting_started`／`meeting_ended` | `TeamLeader` 開始／結束會議 | 建立／結束會議範圍，結束事件啟動整理 |
| `scheduled_job_due` | 排程到點 | 啟動提醒、追問、`TeamLeader` 彙報或每頻道每日摘要 |
| `confirmation_received` | 真人確認操作 | 只套用被確認的不可變草稿，不重新讓模型改寫後直接執行 |
| `bot_message` | Bot 自己的訊息 | 不觸發新一輪一般回答或每日活動；避免摘要與提醒反覆觸發 |

使用者在群聊直接問成員「大家進度如何」且未 @Bot 時，Bot 不回答。會議與每日摘要可以讀取該段內容，但不能因此即時代替成員回答。

## 初始化與設定

`Administrator` 設定 `TeamLeader` 後，AI 私訊 `TeamLeader` 詢問習慣，整理為以下結構。

| 欄位 | 說明與驗證 |
|---|---|
| `timezone` | IANA timezone；`TeamLeader` 確認後才決定相對日期、排程與畫面時間 |
| `remind_before_minutes` | 截止前提醒 offsets；非負、去重、排序 |
| `followup_interval_minutes` | 未回覆後的追問間隔；有追問時必須大於零 |
| `max_followups` | 每次進度詢問週期最多追問次數；可為零 |
| `leader_report_mode` | `event`／`scheduled`／`both` |
| `leader_report_events` | 已勾選的 `blocked`、`overdue`、`no_response`、`progress_updated` 事件；不擅自加入 `TeamLeader` 未選的週期 |
| `leader_report_schedule` | 若選定期彙報，`kind` 為 `interval`、`daily` 或 `weekly`，並提供對應間隔或當地時間 |
| `no_response_report_after_minutes` | 選擇未回覆事件彙報時，設定已送達詢問後多久通知 `TeamLeader`；與追問間隔分開 |
| `daily_summary_time` | 每日摘要的當地時間 |
| `delivery_windows` | 以 `weekdays`、`start`、`end` 表達當地星期與可發訊息時段；窗口可跨日，須明確解析 |

AI 對模糊回答追問，不能把「不要太常催」直接換成自選數值。選擇 `scheduled`／`both` 時必須有 `leader_report_schedule`；選擇 `no_response` 事件時必須有未回覆門檻。設定顯示為可讀摘要供 `TeamLeader` 確認；確認後記錄版本與生效時間，修改時同樣確認。時間區間衝突或無法送出每日摘要時，先指出衝突，不悄悄覆蓋。

## 會議與任務建立

1. `TeamLeader` 在可讀取的文字來源開始會議，記錄 `channel_id`、開始時間及訊息邊界。會議限同一來源，不自行混合其他頻道或私訊。
2. `TeamLeader` 結束會議後，按邊界讀取可取得的成員訊息，產生討論摘要、決議與任務候選。
3. 「@甲 負責登入功能，指定日期時間前完成」且出自 `TeamLeader` 的明確指派，可直接成為正式任務。後端驗證來源作者、`TaskOwner` 身分、時間、必要欄位與對應證據；AI 的 `confirmed=true` 不能取代驗證。
4. 提議、疑問、否定句、缺少 `TaskOwner` 或期限、同名對象無法辨識，轉為提案並追問。明確的相對日期按已確認 timezone 解析並顯示絕對時間；無法唯一解讀時追問。
5. `TaskOwner` 若無來源權限，保留任務及指派依據，設定 `activation_state=awaiting_leader_decision`；先向有權限的 `TeamLeader` 說明。等待 `TeamLeader` 調整分配或由人處理權限，AI 不轉達、不啟動提醒。
6. 在原頻道發布紀錄，分列正式任務與待確認提案。可列出原本已公開的指派；無法啟動的處理提示只先私訊 `TeamLeader`，不在原頻道加入權限／風險評估。公開部分只使用原頻道已有的內容，不帶入私人進度。

任務最少包含工作內容、`TaskOwner`、明確期限、來源及指派依據。`Collaborator` 與成果說明可補充。顯示名稱用於閱讀；實際授權與關聯使用 Discord user ID。

## 任務狀態、進度與異動

| `status` | 意義 | 主要變更來源 |
|---|---|---|
| `not_started` | 已成立、尚未回報開始 | 建立任務 |
| `in_progress` | `TaskOwner` 回報進行中 | `TaskOwner` 的共享回報 |
| `blocked` | `TaskOwner` 明確回報阻礙 | `TaskOwner` 的共享回報 |
| `completed` | `TaskOwner` 明確回報完成 | `TaskOwner` 的共享回報 |
| `cancelled` | `TeamLeader` 取消 | `TeamLeader` 明確指令 |

`overdue` 指尚未完成／取消且已超過 `due_at`；歷史上的晚交另由完成紀錄判斷。`awaiting_progress_reply` 由已送達的詢問及回覆關聯判定。兩者均不是正式狀態。`activation_state` 另表達是否可啟動通知，不能用 `blocked` 代替沒有來源權限的情形。

`TaskOwner` 不能修改正式 `TaskOwner`、期限或取消任務；可以提出修改建議。`Collaborator` 不代替 `TaskOwner` 更新正式進度。非 terminal 任務可以由 `TaskOwner` 明確更正為 `not_started`、`in_progress` 或 `blocked`，並保留更正依據。`TeamLeader` 可以修改分配、期限、取消任務，或將已完成／取消任務重新開啟；重新開啟時明示恢復的狀態與期限。每次異動保存操作者、證據、前後值與版本。

「快好了」只記錄原意或追問，不轉成完成 90%。沒有回覆只代表進度未知。訊息關聯不到唯一任務時，先讓 `TaskOwner` 選擇，不更新多筆猜測任務。

私訊詢問須標示：「本次提交的任務進度將分享給有來源權限的組長」。實作以一份可分享的進度草稿供 `TaskOwner` 確認，確認後才寫入團隊進度並啟動彙報。這個確認流程同時處理私人資訊混入回覆的情況；未確認的一般私聊不進團隊查詢或摘要。預估完成時間是回報，不自動改正式 `due_at`。

## 提醒、追問與 `TeamLeader` 彙報

Scheduler 持久化工作；不靠 PTC 容器長期等待。每次工作執行時重新讀取任務、設定版本、來源權限與可發訊息時段。

- 任務已完成／取消、正在等 `TeamLeader` 處理權限，或該次提醒已送出時，不重送。
- 已送達的詢問才開始計算未回覆時間。訊息送不出去不能被算成「`TaskOwner` 未回覆」。
- `sent` 指 Discord 已接受訊息並回傳 message ID，不代表收件人已讀；彙報不推定閱讀情形。
- Bot 收到可關聯至該詢問的 `TaskOwner` 回覆時，立即記錄收到回覆並停止「未回覆」追問；資料不足或等待分享確認時，只能標為 `needs_clarification`／`awaiting_confirmation`，不能說成未回覆，也不能分享未確認內容。
- 新的共享進度回報使舊詢問週期結束；下一週期依設定產生，不能因同一任務多次 retry 累加追問次數。
- 不在可送時段時，延後至下一有效窗口，再檢查工作是否仍有效。
- 期限／`TaskOwner`／設定改動後，舊版本的待送工作失效，依新資料重算；完成後停用尚未發送的工作。
- `TeamLeader` 回報可包含任務、最新已確認進度、詢問時間、未回覆或阻礙依據與來源。`TeamLeader` 無來源權限的項目不進其彙報，亦不顯示被隱藏項目的數量或標題。
- 週期彙報支援固定分鐘間隔、每日或每週；interval 以設定生效點作錨點。`no_response` 事件依獨立門檻觸發，不把「追問一次」當成 `TeamLeader` 已同意的升級條件。
- DM 失敗記錄 `delivery_failed`，不自動轉到公開頻道。Discord 有 `50007 Cannot send messages to this user` 等錯誤，不能把送出要求等同送達。[Discord API error codes](https://docs.discord.com/developers/topics/opcodes-and-status-codes#json-json-error-codes)

停機後可重算仍有效的工作；先前期限提醒已無意義時不補送過時文案，改依當下任務狀態及已確認的彙報規則處理。補跑也受窗口、去重及當下權限限制。這是避免遺漏與重複的工程細化，不新增提醒頻率。

## 每日摘要

每個有新成員訊息的來源獨立處理。以兩個相鄰的排定時間定義 `[window_start, window_end)`，不是從「上次成功發送時間」切分。今天截止後的訊息進入下次區間；Bot／webhook 自動輸出不計入成員對話。

摘要只含同來源的討論、決議、已公開待辦與未解問題，不帶入私人進度或模型跨來源的風險評估。每日摘要不是第二條自動派工入口；一般聊天中出現的任務想法，可被整理，但正式建檔仍走 `TeamLeader` 明確指令或會議流程。

一個頻道無權限或讀取失敗，不阻止其他頻道的摘要。讀取不完整時標記待重試，不以「今日無新訊息」結案。每個 `(team_id, source_id, window_start, window_end)` 只發布一個正式版本；retry 不改變區間。設定改變的生效時間作為一次邊界，後續按新時間計算，不留空隙、不重複覆蓋。

## 查詢、轉達與權限

### 權限政策類別命名

| Policy class | 規格中的責任 |
|---|---|
| `RoleAuthorizationPolicy` | 檢查操作是否由合適的 `Administrator`、`TeamLeader`、`TaskOwner` 或合法 job 執行 |
| `SourceAccessPolicy` | 檢查使用者與 Bot 對全部依據來源的存取權；衍生資料沿用來源限制 |
| `TaskAssignmentPolicy` | 指派給無來源權限的 `TaskOwner` 時，等待 `TeamLeader` 決定，不修改權限或轉達 |
| `ProgressSharingPolicy` | 私訊草稿只給本人；確認後的共享版本只提供給既定受眾 |
| `ConfirmationPolicy` | 檢查確認者、固定 payload、接收對象與版本；模型不能代替真人確認 |
| `DeliveryPolicy` | 決定合法交付位置，發送前驗權；私訊失敗不轉成公開發送 |
| `ContextIsolationPolicy` | 依使用者、受眾及來源範圍隔離檢索資料、執行上下文與對話歷史 |

以上是既有規則的英文類別名稱，不指定 class 繼承關係或權限套件。存取判斷 `AccessDecision` 的識別值統一為 `allow`、`deny`、`unknown`；`unknown` 不視為 `allow`。

### 存取與來源標籤

每筆資料附 `team_id`、來源集合與可見範圍。衍生資料採來源限制的交集：接收者必須有權讀取所有依據來源。後端在資料交給 Claude／PTC 之前先篩選，在實際發送前再驗證；system prompt 不是驗權機制。

來源清單由 handler 追蹤，不接受模型任意縮減。未被引用但已進入同一執行上下文的資訊仍可能影響輸出；輸出至少沿用該執行 compartment 的來源限制。channel 摘要只建立單來源 run；不同使用者、不同接收對象或不同權限範圍不共用 PTC 容器及對話歷史。這是本專案的隔離設計。

一般私訊的草稿只能給本人看；`TaskOwner` 確認後產生一筆新的共享進度，指定本人及「有任務來源權限的 `TeamLeader`」為受眾。共享版本不自動授權其他 `TeamMember`。讀過這筆進度的執行上下文不能直接產生公開 channel 摘要。

歷史訊息需考慮有效的 `VIEW_CHANNEL`、`READ_MESSAGE_HISTORY` 與 Bot 內容取得能力；private thread 還需確認 membership 等條件。Discord 的 `MESSAGE_CONTENT` intent 與頻道權限是不同條件，只有 @Bot 的內容例外不足以提供完整會議或每日摘要。[Discord Gateway](https://docs.discord.com/developers/events/gateway#message-content-intent)、[Message resource](https://docs.discord.com/developers/resources/message#get-channel-messages)、[Threads](https://docs.discord.com/developers/topics/threads)

### 交付政策

| `policy_case` | 中文情境 | 處理 |
|---|---|---|
| `unaddressed_channel_message` | 一般群聊、無 @Bot／指令 | 不回答 |
| `same_channel_query` | 頻道提問，只使用同頻道資料 | 可在原處回覆，但仍檢查 Bot 發言權與來源限制 |
| `cross_source_channel_query` | 頻道提問需要其他來源 | 原處僅說明「將以私訊回答」；對提問者驗權後私訊交付 |
| `cross_source_direct_query` | 跨來源私訊查詢 | 只檢索該人目前可讀的來源；無權部分不進模型 |
| `leader_without_source_access` | `TeamLeader` 無來源權限 | 不因 `TeamLeader` 身分提供內容 |
| `owner_without_source_access` | `TaskOwner` 無來源權限 | 先告知有權限的 `TeamLeader`，等待決定，不轉達 |
| `source_access_unavailable` | 權限無法確認／來源頻道已刪除 | 暫停該來源的內容交付，記錄待處理，不以歷史快取放行 |
| `direct_message_delivery_failed` | 私訊失敗 | 記錄 `delivery_failed`，沒有自動公開 fallback |

可分辨時回覆「你沒有權限取得所要求的資訊」「Bot 沒有權限讀取所要求的來源」或「沒有找到符合條件的資料」。不得在錯誤中透露使用者原本不知道的私人頻道名稱、任務標題或隱藏結果數量；無法安全辨別時只說明無法驗證或取得所要求資料。

### 錯誤類別命名

程式以英文 `ErrorCode` 判斷原因，繁體中文 `message` 用於對使用者說明。權限相關錯誤及既有 tool 錯誤統一如下；不得以錯誤文字洩漏不可見內容。

| `ErrorCode` | 中文含義 |
|---|---|
| `INVALID_ARGUMENT` | 參數或格式不符 |
| `ACCESS_DENIED_USER` | 使用者沒有來源存取權 |
| `SOURCE_UNAVAILABLE_BOT` | Bot 無法讀取要求的來源 |
| `PERMISSION_UNVERIFIED` | 無法確認目前權限 |
| `NOT_FOUND` | 在可安全識別的範圍內沒有符合資料 |
| `ROLE_REQUIRED` | 操作者不具備該操作所需的業務身分 |
| `CONFIRMATION_REQUIRED` | 所要求執行的版本尚未經真人確認 |
| `INVALID_EVIDENCE` | 來源參照無效、跨範圍或證據不符 |
| `VERSION_CONFLICT` | 資源版本已變動 |
| `STALE_JOB` | 排程工作已失效 |
| `DESTINATION_NOT_ALLOWED` | 目的地或接收者不符合來源與確認限制 |
| `RATE_LIMITED` | 上游服務限制呼叫頻率 |
| `UPSTREAM_UNAVAILABLE` | 上游服務暫時不可用 |

`needs_clarification`、`awaiting_confirmation`、`awaiting_leader_decision` 是業務結果的 `state`，不是上述 `ErrorCode`。例如對無來源權限的 `TaskOwner` 保留指派，是 `awaiting_leader_decision`，不能記成任務已轉達或已啟動。

### 一般代為轉達

只因 `TeamLeader` 明確要求而啟動。AI 整理內容及接收對象，`TeamLeader` 確認該版本後再發送，標示「代組長轉達」。確認內容變動、收件人增加或來源範圍改變時，舊確認失效。`TeamLeader` 確認不能覆蓋接收者的來源限制。

向 channel 轉達私人來源內容時，只有能證明該位置的受眾均符合來源限制才可發送；無法證明就先請 `TeamLeader` 改選合法接收對象。AI 不自行變更收件名單或改成公開公告。

## 概念資料模型

| Entity | 主要欄位與用途 |
|---|---|
| `Team` | `id, guild_id, leader_user_id, version`；避免固定全域 `TeamLeader` |
| `TeamSettings` | `team_id, version, confirmed_by, effective_at` 與排程設定 |
| `SourceRef` | opaque `id, team_id, channel_id, thread_id?, message_id?, author_id, captured_at, content_digest, evidence_excerpt` |
| `Meeting` | `id, team_id, source_id, started_at, ended_at, boundary_ids, state, version` |
| `Task` | `id, team_id, title, description, owner_user_id, collaborators, due_at, status, activation_state, source_refs, version` |
| `TaskChange` | `task_id, old_version, new_version, actor_id, reason, before, after, source_refs` |
| `ProgressUpdate` | `task_id, owner_id, status, shared_text, blockers, estimated_completion_at?, confirmed_at, inquiry_id?, source_refs` |
| `Inquiry` | `id, task_id, owner_id, delivery_id, sent_at, reply_received_at?, shared_progress_id?, state, followup_count, version`；`state` 以 `awaiting_reply`、`reply_received`、`closed` 區分未回覆、已回覆待釐清／確認與結案 |
| `PendingAction` | `id, kind, immutable_payload, payload_digest, required_confirmer, state, source_refs, base_version, confirmed_at?` |
| `Artifact` | `id, purpose, content, source_refs, audience_policy, destination_binding, approval_state, version`；所有可交付輸出的依據 |
| `ScheduledJob` | `id, team_id, kind, task_id?, source_id?, settings_version, task_version?, scheduled_at, state, dedupe_key` |
| `Delivery`／outbox | `id, artifact_id, destination, state, provider_message_id?, attempts, last_error, dedupe_key` |
| `AuditEvent` | `request_id, actor/job_id, tool, resource_id, result_code, version, timestamp`；避免把完整私訊寫進 log |

所有時間戳保存為 UTC RFC 3339；畫面按設定 timezone 顯示。每日排程保存 timezone，不以固定 UTC offset 取代。來源與共享進度的限制保存在後端，不能只存在向量資料庫或 prompt 中。

### 既有狀態與類型識別值

| 欄位／用途 | English values |
|---|---|
| `Task.status` | `not_started`、`in_progress`、`blocked`、`completed`、`cancelled` |
| `Task.activation_state` | `active`、`awaiting_leader_decision` |
| `Inquiry.state` | `awaiting_reply`、`reply_received`、`closed`；`reply_received` 不代表內容已確認分享 |
| `Delivery.state` | `queued`、`sent`、`delivery_failed`、`delivery_unknown` |
| `Artifact.purpose` | `summary`、`task_notice`、`leader_report`、`announcement`、`query_answer`、`confirmation_preview` |
| `ToolResult.data.state` | `needs_clarification`、`awaiting_confirmation`、`awaiting_leader_decision`、`ready`、`queued` |

欄位名稱、狀態與用途識別值用於程式／儲存；「待開始」「已完成」「未送達」等中文只作顯示與說明，不作 enum 值。未在既有流程中定義的執行中間狀態，待恢復規劃後再補，不在本次新增 state machine。

`activation_state` 為 `active` 或 `awaiting_leader_decision`。查驗服務失敗另記工作／交付錯誤，不錯稱 `TaskOwner` 已失去權限。原來源權限恢復後也先呈報 `TeamLeader`，按其決定解除暫停，不讓背景掃描默默執行尚待決定的轉達。

原訊息刪除不自動刪除已成立任務與必要證據；原來源頻道的限制仍保留。一般聊天不長期完整保存，會議期間可有完成整理所需的暫存。未指定固定保存天數；不在文件中編造期限。備份與實際清理政策由部署方案落實。

## PTC 與執行可靠性

PTC 只負責一次工作中的工具組合。後端保留任務、排程、確認草稿與 outbox，不能依賴容器作永久 database。啟動時檢查選定模型是否支援 PTC；詳細 API 執行契約依 [Anthropic PTC 文件](https://platform.claude.com/docs/zh-TW/agents-and-tools/tool-use/programmatic-tool-calling)。

人類確認與訊息送達採持久化流程：工具回傳 `awaiting_confirmation` 或 `queued` 後即結束，不在 tool call 裡等待真人按鈕或長期送達。確認事件到來後開新工作。

有寫入或發送副作用的操作使用 idempotency 與版本檢查。資料庫中的任務／outbox 寫入可用交易保證；外部 Discord 發送若結果不明，不宣稱 exactly-once，記錄 `delivery_unknown` 並先 reconciliation。未查明前不能用不同 key 盲目重送。

## 驗收情境

以下是預定測試案例與 expected，尚未宣稱執行。

| ID | 操作／條件 | Expected |
|---|---|---|
| AC01 | `TeamLeader` 明確指定甲與完整期限後結束會議 | 一筆正式任務、來源可追溯、原頻道紀錄；符合設定才啟動提醒 |
| AC02 | 成員說「要不要讓甲做，下週應該來得及」 | 待確認，不直接建正式任務 |
| AC03 | 同一會議結束事件或 tool call 重試 | 不重複建相同指派或重複發同一版本紀錄 |
| AC04 | `TaskOwner` 無來源權限 | 指派等 `TeamLeader` 決定；只先通知有權限的 `TeamLeader`，不轉達、不改權限 |
| AC05 | `TeamLeader` 與 `TaskOwner` 都無該來源權限 | 兩者均收不到內容；留下受限的內部待處理紀錄 |
| AC06 | 群聊問進度且未 @Bot | Bot 不代答 |
| AC07 | @Bot 查到其他有權來源 | 原處只提示改私訊；答案私訊給已驗權提問者 |
| AC08 | `TeamLeader` 要求無權來源／Bot 無讀取權／查無資料 | 安全可辨識時回覆不同原因，不揭露隱藏內容 |
| AC09 | 到提醒時間，但在禁發窗口或任務已完成 | 延後有效工作；完成任務不送 |
| AC10 | DM 發送失敗 | 記錄 delivery_failed，沒有公開 fallback，也不計為已詢問未回覆 |
| AC11 | `TaskOwner` 回覆「快好了」 | 不自行標記完成或產生百分比 |
| AC12 | `TaskOwner` 的回覆混有私人內容 | 只向本人顯示分享草稿，確認後才讓 `TeamLeader` 讀到共享版本 |
| AC13 | `Collaborator` 回報、或 `TaskOwner` 要求改正式期限 | 不直接套用越權異動；可形成給 `TeamLeader` 的提案 |
| AC14 | 有已送達詢問但沒有回覆 | 依設定追問／彙報，文字明示進度未知及詢問依據 |
| AC15 | 某頻道只有 Bot 摘要與提醒 | 不產生新的每日摘要 |
| AC16 | 截止後有新訊息，且本次摘要 retry | 新訊息進下一區間；本次維持原邊界且不重複發布 |
| AC17 | 摘要時某頻道讀取失敗 | 該頻道待重試，其他可處理頻道正常，不假稱無對話 |
| AC18 | 編輯／刪除原指派訊息 | 正式任務不自動取消或改期限；保存必要依據及來源限制 |
| AC19 | `TeamLeader` 改期限或重指派，舊提醒同時執行 | 版本檢查使舊工作失效，不傳給舊 `TaskOwner` |
| AC20 | 轉達草稿確認後改內容或收件人 | 原確認不能授權新版本 |
| AC21 | 模型偽造 actor、來源、確認或 job | 後端拒絕；不能透過 PTC 繞過 handler |
| AC22 | 兩人使用同一 team 但來源權限不同 | 模型上下文、PTC 容器與檢索結果隔離 |
| AC23 | 權限在產生答案後、送出前被撤銷 | 發送前攔截，不能靠舊快取放行 |
| AC24 | PTC 逾時後重試已寫入任務／已排入 outbox 的操作 | 回傳原操作結果，不再造成一次業務副作用 |
| AC25 | `TaskOwner` 已回覆，但待釐清或尚未確認分享草稿 | 停止未回覆計時；不誤報沉默，也不洩漏未確認內容 |
| AC26 | 可讀 parent channel，但不符合 private thread 存取條件 | 不取得或交付該 thread 內容，也不混入 parent 的摘要 |

## 待實作時決定的技術參數

程式語言、database、Discord SDK、Claude model ID、部署平台、指令命名、handler timeout／retry 上限與頁面大小屬於實作配置。它們未經本次訪談指定，不在此冒充既定選擇。模型須通過 PTC capability 檢查；效能與 API 費用需用實際整合測量，這份 spec 沒有宣稱數值。
