版本：v1.2｜2026-11-21｜狀態：implementation_paused

# Team AI Assistant 功能與系統 spec

**Index**

- [1. 目的](#1-目的)
  - [1.1 適用範圍](#11-適用範圍)
- [2. 系統 spec](#2-系統-spec)
  - [2.1 系統命名規則](#21-系統命名規則)
  - [2.2 角色與權責](#22-角色與權責)
  - [2.3 事件與啟動條件](#23-事件與啟動條件)
  - [2.4 任務狀態與異動權限](#24-任務狀態與異動權限)
    - [2.4.1 任務狀態與追蹤欄位](#241-任務狀態與追蹤欄位)
    - [2.4.2 任務異動權限](#242-任務異動權限)
  - [2.5 權限、來源與訊息交付](#25-權限來源與訊息交付)
    - [2.5.1 權限政策類別命名](#251-權限政策類別命名)
    - [2.5.2 存取與來源標籤](#252-存取與來源標籤)
    - [2.5.3 交付政策](#253-交付政策)
    - [2.5.4 錯誤類別命名](#254-錯誤類別命名)
  - [2.6 概念資料模型](#26-概念資料模型)
    - [2.6.1 既有狀態與類型識別值](#261-既有狀態與類型識別值)
- [3. 功能 spec](#3-功能-spec)
  - [3.1 已確認的功能需求](#31-已確認的功能需求)
  - [3.2 初始化與設定](#32-初始化與設定)
  - [3.3 會議與任務建立](#33-會議與任務建立)
  - [3.4 提醒、追問與](#34-提醒追問與-teamleader-彙報) `TeamLeader` [彙報](#34-提醒追問與-teamleader-彙報)
    - [3.4.1 任務進度回報](#341-任務進度回報)
    - [3.4.2 排程提醒](#342-排程提醒)
    - [3.4.3 未回覆追問](#343-未回覆追問)
    - [3.4.4 組長彙報](#344-組長彙報)
  - [3.5 每日摘要](#35-每日摘要)
  - [3.6 一般代為轉達](#36-一般代為轉達)
  - [3.7 工具定義與呼叫](#37-工具定義與呼叫)
    - [3.7.1 工具定義（Function Tools）](#371-工具定義function-tools)
    - [3.7.2 工具呼叫方式](#372-工具呼叫方式)
    - [3.7.3 確認、重試與訊息送達](#373-確認重試與訊息送達)
- [4. 驗收](#4-驗收)
- [5. 待決定](#5-待決定)

## 1. 目的

Team AI Assistant（以下簡稱 Assistant）支援 Discord 上的團隊合作。組長（`TeamLeader`）確認工作內容與分工，組員（`TeamMember`）參與討論與執行。Assistant 協助組長把文字會議的決議整理成可追蹤的任務。

每筆任務有一位主責（`TaskOwner`），負責回報該任務的進度。Assistant 依組長的設定提醒主責、詢問進度，並將有依據的進度及風險彙報給組長。

### 1.1 適用範圍

- **團隊與頻道。** 第一版使用一個 Discord 伺服器，支援一個團隊和一位組長。團隊可以在多個文字頻道（channel）協作，各頻道的資訊仍受各自的存取權限限制。
- **文字輸入。** Assistant 只查閱有權取得的文字。文字討論串（thread）是獨立的來源，適用相同的查詢與摘要規則。讀取私人討論串時，另須檢查成員資格。
- **第一版的功能邊界。** 語音轉錄、附件內容解析和跨伺服器協作留待後續規劃。

## 2. 系統 spec

### 2.1 系統命名規則

下表所列的類別、資料型別、政策、欄位、角色識別值、事件、狀態、錯誤代碼與 Discord 原生權限，統一使用英文名稱或英文程式值。

| 命名對象 | 格式 | 範例 |
|---|---|---|
| 類別／資料型別／政策類別 | `PascalCase` | `Task`、`TaskOwner`、`SourceAccessPolicy` |
| 欄位／角色識別值／事件／狀態 | `snake_case` | `owner_user_id`、`team_leader`、`meeting_ended`、`awaiting_confirmation` |
| 錯誤代碼／Discord 原生權限 | `UPPER_SNAKE_CASE` | `ACCESS_DENIED_USER`、`VIEW_CHANNEL` |

- **規格說明與訊息。** 系統／功能 spec 的說明、使用者發言及顯示給使用者的訊息使用繁體中文。
- **已定義的欄位與固定值。** 欄位名稱沿用規格中的英文寫法，例如 `owner_user_id`。狀態欄位可接受的固定值也沿用已定義的英文值，例如 `not_started`（待開始）。
- **產品名稱與程式名稱。** 正文以 Assistant 指稱 AI 助理。事件識別值與錯誤代碼沿用已定義的拼法。

### 2.2 角色與權責

| 英文名稱 | 中文名稱 | 識別值 | 操作權限 |
|---|---|---|---|
| `Administrator` | 管理者 | `administrator` | 透過 Assistant 的設定介面驗證身分，指定伺服器對應的團隊與組長。 |
| `TeamLeader` | 組長 | `team_leader` | 確認設定／開始與結束會議／正式指派與修改任務／取消與重開任務／確認代為轉達的內容與對象。 |
| `TeamMember` | 組員 | `team_member` | 依來源權限參與對話／查詢／提出建議。組員身分本身不授予正式指派或異動權限。 |
| `TaskOwner` | 主要負責人／主責 | `task_owner` | 回報自己負責的任務進度／阻礙／完成情形，並確認可分享的回報版本。 |
| `Collaborator` | 協作者 | `collaborator` | 協助完成所列的任務，正式進度由該任務的主責回報。 |
| `AIAssistant` | AI 助理（Assistant） | `ai_assistant` | 整理資訊／擷取任務／追問／提出建議／依排程提醒與彙報。只能使用已授予的存取權限。 |
| `Scheduler` | 排程系統 | `scheduler` | 依已確認的設定建立／延後／取消排程工作。工作到點時，驗證後只可啟動該工作指定的提醒／追問／組長彙報／每日摘要。 |

- **單筆任務的分工。** `TaskOwner` 與 `Collaborator` 只適用於該筆任務，分別記在主要負責人的使用者識別值（`owner_user_id`）與協作者清單（`collaborators`）。組長也可以擔任某筆任務的主責。
- **Assistant 的權限。** Assistant 使用已授予的權限執行工作。不得自行提高資訊存取權或修改 Discord 權限。
- **排程系統的權限。** 排程系統只按工作授權。到點時須重新檢查任務、設定版本、來源權限與可發訊息時段。組長的任務指派及確認權限由組長本人行使。
- **操作權限與讀取權限。** 組長可以執行上表的操作，但讀取來源仍須檢查目前有效的 Discord 頻道權限。判斷需同時考慮 Discord 角色與頻道的個別權限設定。 [Discord Permissions](https://docs.discord.com/developers/topics/permissions)

### 2.3 事件與啟動條件

| `trigger_kind` | 觸發條件 | 系統處理 |
|---|---|---|
| `member_message` | 收到一般成員訊息 | 可記錄每日活動進度（watermark），或納入已啟動的會議。 |
| `bot_mentioned`／`command_invoked` | 成員標註 @Assistant／送出明確指令 | 依已驗證的操作者身分啟動查詢／指令。 |
| `direct_message_received` | 收到使用者直接傳給 Assistant 的私訊 | 依既定設定辨識伺服器／團隊，處理該人的查詢／任務回報。 |
| `meeting_started`／`meeting_ended` | 組長明確開始／結束會議 | 記錄會議範圍。收到結束事件後啟動整理。 |
| `scheduled_job_due` | 已安排的工作到點 | 排程系統依工作類型啟動提醒／追問／組長彙報／每日摘要。 |
| `confirmation_received` | 收到真人確認 | 只執行已確認的草稿內容。模型不得改寫後直接執行。 |
| `bot_message` | Assistant 發出訊息 | 不啟動下一輪回答或每日活動計算，避免重複觸發摘要與提醒。 |

- 表中的名稱是本專案的內部事件識別值。Discord SDK 的原生事件名稱仍在接收 Discord 訊息時使用。
- 一般成員訊息可先記錄活動或供後續整理，無須每則都呼叫模型。

### 2.4 任務狀態與異動權限

#### 2.4.1 任務狀態與追蹤欄位

| 類別 | 狀態值／欄位 | 意義 | 變更來源／判定條件 |
|---|---|---|---|
| 任務狀態（`status`） | `not_started` | 待開始 | 任務成立，主責尚未回報開始。 |
| 任務狀態（`status`） | `in_progress` | 進行中 | 主責回報進行中。 |
| 任務狀態（`status`） | `blocked` | 有工作阻礙 | 主責明確回報受到阻礙。 |
| 任務狀態（`status`） | `completed` | 已完成 | 主責明確回報完成。 |
| 任務狀態（`status`） | `cancelled` | 已取消 | 組長明確取消任務。 |
| 追蹤標記 | `overdue` | 已超過正式期限（`due_at`） | 任務尚未完成／取消，且目前時間已超過期限。曾否逾期完成依完成紀錄判定。 |
| 追蹤標記 | `awaiting_progress_reply` | 等待進度回覆 | 進度詢問已送達，尚未收到可關聯的回覆。 |
| 通知啟用狀態 | `activation_state` | 任務通知是否可啟動 | 來源權限有問題時，暫停相關通知並記錄在此欄位。 |

- **任務狀態。** `status` 表示工作進行到哪個階段，每筆任務同一時間只有一個值。
- **追蹤標記。** 逾期和等待回覆各自判定，一筆進行中的任務可以同時有兩個標記。
- **通知啟用狀態。** `activation_state` 表示相關通知能否啟動。來源權限造成的通知暫停由此欄位表示，工作本身受阻時才將 `status` 記為 `blocked`。

#### 2.4.2 任務異動權限

| 角色 | 可執行的異動／限制 |
|---|---|
| 主責（`TaskOwner`） | 可明確將尚未完成／取消的任務更正為 `not_started`／`in_progress`／`blocked`，並保留更正依據。可提出修改建議，正式指派／改期限／取消由組長處理。 |
| 協作者（`Collaborator`） | 可以協助執行任務，正式進度由主責更新。 |
| 組長（`TeamLeader`） | 可修改分配／期限、取消任務，或重開已完成／取消的任務。重開時明示恢復的狀態與期限。 |

- **異動紀錄。** 每次異動保存操作者、證據、前後值與版本。

### 2.5 權限、來源與訊息交付

#### 2.5.1 權限政策類別命名

| Policy class | 規格中的責任 |
|---|---|
| `RoleAuthorizationPolicy` | 檢查操作是否由合適的 `Administrator`、`TeamLeader`、`TaskOwner` 或合法 job 執行 |
| `SourceAccessPolicy` | 檢查使用者與 Assistant 對全部依據來源的存取權；衍生資料沿用來源限制 |
| `TaskAssignmentPolicy` | 指派給無來源權限的 `TaskOwner` 時，等待 `TeamLeader` 決定，不修改權限或轉達 |
| `ProgressSharingPolicy` | 私訊草稿只給本人；確認後的共享版本只提供給既定受眾 |
| `ConfirmationPolicy` | 檢查確認者、固定 payload、接收對象與版本；模型不能代替真人確認 |
| `DeliveryPolicy` | 決定合法交付位置，發送前驗權；私訊失敗不轉成公開發送 |
| `ContextIsolationPolicy` | 依使用者、受眾及來源範圍隔離檢索資料、執行上下文與對話歷史 |

- **存取判斷。** `AccessDecision` 使用 `allow`（允許）、`deny`（拒絕）或 `unknown`（無法確認）。只有 `allow` 可以放行。

#### 2.5.2 存取與來源標籤

- **資料標籤。** 每筆資料記錄團隊識別碼（`team_id`）、依據來源及可見範圍。
- **多來源授權。** 使用多個來源產生結果時，接收者必須有權讀取每個依據來源。後端在把資料交給模型或回傳給工具呼叫流程之前篩選，實際發送前再驗證。系統提示無法授予存取權限。
- **追蹤全部來源。** 來源清單由後端處理程式記錄，模型不能自行刪減。凡是進入同一次模型處理的來源都會限制輸出的交付範圍，包括未直接引用的內容。
- **隔離模型工作。** 頻道摘要每次只使用一個來源。不同使用者、接收對象或權限範圍的工作須隔離檢索資料、程式化呼叫的執行上下文及對話歷史。
- **私訊與共享進度。** 私訊草稿只提供給本人。主責確認後，另存一筆共享進度，只提供給主責和有任務來源權限的組長。使用過共享進度的模型工作不能直接用來產生公開頻道摘要。
- **Discord 歷史訊息。** 同時檢查 `VIEW_CHANNEL`、`READ_MESSAGE_HISTORY` 及 Assistant 取得訊息內容的能力。私人討論串另查成員資格。`MESSAGE_CONTENT` 是獨立的 Discord 事件設定，僅有標註 @Assistant 的內容例外不足以整理完整會議或每日摘要。 [Discord Gateway](https://docs.discord.com/developers/events/gateway#message-content-intent) · [Message resource](https://docs.discord.com/developers/resources/message#get-channel-messages) · [Threads](https://docs.discord.com/developers/topics/threads)
- **已封存的討論串。** 訊息讀取元件（adapter）按需查閱有權取得的歷史。Gateway 尚未同步討論串時，先檢查可讀歷史再判斷是否有對話。

#### 2.5.3 交付政策

| `policy_case` | 中文情境 | 處理 |
|---|---|---|
| `unaddressed_channel_message` | 一般群聊、無 @Assistant／指令 | 不回答 |
| `same_channel_query` | 頻道提問，只使用同頻道資料 | 可在原處回覆，但仍檢查 Assistant 發言權與來源限制 |
| `cross_source_channel_query` | 頻道提問需要其他來源 | 原處僅說明「將以私訊回答」；對提問者驗權後私訊交付 |
| `cross_source_direct_query` | 跨來源私訊查詢 | 只檢索該人目前可讀的來源；無權部分不進模型 |
| `leader_without_source_access` | `TeamLeader` 無來源權限 | 不因 `TeamLeader` 身分提供內容 |
| `owner_without_source_access` | `TaskOwner` 無來源權限 | 先告知有權限的 `TeamLeader`，等待決定，不轉達 |
| `source_access_unavailable` | 權限無法確認／來源頻道已刪除 | 暫停該來源的內容交付，記錄待處理，不以歷史快取放行 |
| `direct_message_delivery_failed` | 私訊失敗 | 記錄 `delivery_failed`，沒有自動公開 fallback |

- **原因可安全區分時。** 分別告知是使用者無權取得、Assistant 無權讀取，或查無資料。
- **原因無法安全區分時。** 只告知無法驗證或取得資料。錯誤訊息不得透露接收者無法取得的私人頻道名稱、任務標題或隱藏結果數量。
- **權限查驗失敗。** 記為工作／交付錯誤，主責的權限維持待查驗。
- **來源權限恢復。** 先通知組長，等組長決定解除暫停後，才執行先前待處理的轉達。

#### 2.5.4 錯誤類別命名

| `ErrorCode` | 錯誤原因（中文） |
|---|---|
| `INVALID_ARGUMENT` | 參數或格式不符 |
| `ACCESS_DENIED_USER` | 使用者沒有來源存取權 |
| `SOURCE_UNAVAILABLE_BOT` | Assistant 無法讀取要求的來源 |
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

- **錯誤代碼（**`ErrorCode`**）。** 程式用它識別原因。表中的「錯誤原因（中文）」供閱讀規格時查閱。
- **顯示訊息（**`message`**）。** Assistant 在實際操作失敗時提供給使用者的繁體中文文字，依情境組成。訊息可揭露的資訊依第 2.5.3 節判斷。

### 2.6 概念資料模型

- **伺服器識別碼（**`guild_id`**）。** 標示資料與操作屬於哪個 Discord 伺服器。
- **團隊識別碼（**`team_id`**）。** 標示資料與操作屬於哪個團隊，對應團隊紀錄的 `Team.id`。

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

- **時間欄位。** 時間戳以 UTC 儲存，格式採 RFC 3339。畫面依已設定的時區顯示。每日排程保存時區名稱，以便按當地時間執行。
- **權限資料。** 來源限制和共享進度的可見範圍由後端保存與驗證。向量資料庫與模型提示中的資訊不能作為放行依據。
- **原訊息刪除。** 已成立的任務和必要證據仍保留，依原來源權限交付。
- **聊天保存。** 一般聊天不長期完整保存。會議期間只暫存整理所需的內容。
- **資料留存。** 保存期限、備份及清理規則在部署時決定。
- **正式任務的必要資料。** 至少包含工作內容、主責、明確期限、來源及指派依據。協作者及成果說明可補充。
- **期限解析。** 可唯一解讀的相對日期依已確認的時區解析，並顯示明確日期與時間。日期有歧義時請組長釐清。
- **身分關聯。** 顯示名稱供閱讀。授權及資料關聯使用 Discord 使用者 ID。

#### 2.6.1 既有狀態與類型識別值

| 欄位／用途 | English values |
|---|---|
| `Task.status` | `not_started`、`in_progress`、`blocked`、`completed`、`cancelled` |
| `Task.activation_state` | `active`、`awaiting_leader_decision` |
| `Inquiry.state` | `awaiting_reply`、`reply_received`、`closed`；`reply_received` 不代表內容已確認分享 |
| `Delivery.state` | `queued`、`sent`、`delivery_failed`、`delivery_unknown` |
| `Artifact.purpose` | `summary`、`task_notice`、`leader_report`、`announcement`、`query_answer`、`confirmation_preview` |
| `ToolResult.data.state` | `needs_clarification`、`awaiting_confirmation`、`awaiting_leader_decision`、`ready`、`queued` |

- **處理結果（**`ToolResult.data.state`**）。** `needs_clarification` 表示等補充資料。`awaiting_confirmation` 表示等真人確認。`awaiting_leader_decision` 表示等組長決定。實際的處理步驟由各功能規格定義。

## 3. 功能 spec

### 3.1 已確認的功能需求

「實作歸屬」沿用 [2.2](#22-角色與權責) 的角色，標示功能提供給哪個角色操作，或由哪個系統角色執行。

| ID | 實作歸屬 | 規則 |
|---|---|---|
| R01 | `Administrator` | 管理者設定一個 Discord 伺服器對應的團隊與組長，保留多團隊擴充。 |
| R02 | Assistant | 採用 OpenAI Responses API 的直接函式呼叫與程式化工具呼叫。自訂函式由後端驗證及執行。見 [3.7](#37-工具定義與呼叫)。 |
| R03 | `TeamLeader`／`TeamMember`／Assistant | 成員可依權限查詢。Assistant 只在群聊收到 @Assistant 或明確指令時回答，組長的查詢以私訊為主。 |
| R04 | `TeamLeader`／Assistant | Assistant 詢問組長偏好、整理設定，組長確認後啟用。 |
| R05 | `TeamLeader`／Assistant | 組長開始／結束文字會議，Assistant 於會後在原頻道發布紀錄。 |
| R06 | `TeamLeader`／Assistant | 組長明確指定工作、主責與期限時，Assistant 建立正式任務。歧義或缺漏先追問。 |
| R07 | `TeamLeader` | 組長為每筆任務指定一位主責，可另列協作者。 |
| R08 | `TaskOwner`／`TeamLeader`／Assistant | 主責與組長各依權限更新任務。Assistant 分開記錄五種正式狀態及逾期／未回覆標記。 |
| R09 | `TeamLeader`／`Scheduler` | 組長設定提醒、追問、彙報週期及可發訊息時段。排程系統依設定啟動工作。 |
| R10 | Assistant | Assistant 私訊主責提醒，私訊有來源權限的組長彙報進度／風險，並記錄發送結果。 |
| R11 | `TaskOwner`／Assistant | 主責明確回報進度。Assistant 保留原意，避免推定完成或編造百分比，彙報風險時附上依據。 |
| R12 | `TaskOwner`／Assistant | Assistant 先告知進度的分享對象，主責確認草稿後才分享。一般私聊留在原對話。 |
| R13 | `TeamLeader`／`Scheduler`／Assistant | 組長設定每日摘要時間，排程系統觸發。Assistant 在有成員新訊息的原頻道發布摘要。 |
| R14 | `TeamLeader`／Assistant | 組長確認轉達內容與對象，Assistant 驗權後發送並標示「代組長轉達」。 |
| R15 | Assistant | 衍生資料沿用來源限制，組長也須驗權。可以安全區分時，分別說明使用者無權、Assistant 無權或查無資料。 |
| R16 | Assistant | 頻道內的跨來源查詢先告知改用私訊，再驗權並交付答案。 |
| R17 | Assistant | 保存必要的專案資料與證據。原訊息編輯／刪除後，已成立的任務維持原狀。 |
| R18 | `TeamLeader`／Assistant | 主責缺少來源權限時，Assistant 暫停轉達與提醒，請有權限的組長決定如何處理。 |

### 3.2 初始化與設定

- **指定組長。** `Administrator` 先設定 `TeamLeader`。
- **收集設定。** Assistant 私訊組長詢問偏好，整理為下表的欄位。

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

- **缺少明確設定時。** Assistant 詢問組長補充，等組長提供可驗證的值。
- **設定相依性。** 選擇 `scheduled`／`both` 時須提供 `leader_report_schedule`。選擇 `no_response` 時須提供未回覆多久後通知組長（`no_response_report_after_minutes`）。
- **確認後生效。** Assistant 用易讀的摘要呈現設定，組長確認後才生效，並記錄版本與生效時間。修改設定也須重新確認。
- **時間衝突。** 可發訊息時段衝突或無法安排每日摘要時，先向組長指出衝突，由組長決定如何調整。

### 3.3 會議與任務建立

**會議流程**

1. **開始會議。** 組長在可讀取的文字來源開始會議。Assistant 記錄頻道（`channel_id`）、開始時間及訊息邊界，會議輸入限於同一來源。
2. **結束並整理。** 組長結束會議後，Assistant 依訊息邊界讀取可取得的成員訊息，整理摘要、決議及任務候選。
3. **判定任務。** Assistant 依下表區分正式任務與待確認提案。正式指派另檢查主責的來源權限。
4. **發布紀錄。** Assistant 在原頻道分列正式任務與待確認提案，可列出原頻道已有的指派。公開紀錄只用原頻道的內容。任務無法啟用時，相關權限或風險提示只私訊有權限的組長。

| 任務判定條件 | 處理方式 |
|---|---|
| 組長明確指定工作、一位可辨識的主責及期限 | 可直接建立正式任務。後端驗證來源作者、主責身分、時間、必要欄位及對應證據。Assistant 產生的 `confirmed=true` 不構成驗證依據。 |
| 只提議或詢問、否定指派、缺少主責／期限，或無法辨識對象／日期 | 保留為待確認提案，請組長釐清。 |
| 正式指派的主責缺少來源權限 | 保留任務與指派依據，設為 `activation_state=awaiting_leader_decision`，私訊仍有權限的組長。等待組長調整指派或由人處理權限。等待期間暫停轉達及提醒。 |

- 正式任務的欄位、期限解析及身分關聯共用 [2.6](#26-概念資料模型) 的規則。

### 3.4 提醒、追問與 `TeamLeader` 彙報

| 共用規則 | 系統處理 |
|---|---|
| 排程驗證 | 排程系統（`Scheduler`）保存工作，由後端到點處理。執行前重新檢查任務、設定版本、來源權限及可發訊息時段。 |
| 可發訊息時段 | 時段外先延到下一個可發時段，再檢查工作是否仍有效。 |
| 版本異動 | 期限／主責／設定變更後，原工作版本失效，依新資料重算。任務完成後停用尚未發出的提醒及詢問。 |
| 私訊結果 | `sent` 表示 Discord 已接受並回傳訊息 ID，已讀情形仍未知。失敗記為 `delivery_failed`。私訊失敗時不改發公開訊息。 [Discord 交付錯誤](https://docs.discord.com/developers/topics/opcodes-and-status-codes#json-json-error-codes) |
| 停機恢復 | 只重算仍有效的工作。已失去時效的期限提醒不補發，後續依目前任務狀態及已確認的彙報規則處理。補跑仍遵守發送時段、去重及當下權限。 |

#### 3.4.1 任務進度回報

1. **先告知分享對象。** Assistant 私訊詢問進度時，須提示「本次提交的任務進度將分享給有來源權限的組長」。
2. **確認對應任務。** 若訊息無法唯一對應到一筆任務，Assistant 先請主責選擇，確認後才處理。
3. **依回報原意整理。** 回報不明確時保留原意或追問。沒有回覆時，進度維持未知。主責提供的預估完成時間只記入進度回報，正式期限（`due_at`）維持原值。
4. **確認後才寫入及彙報。** Assistant 私訊主責可分享的進度草稿，讓他確認要分享的內容。回覆混有私人資訊時，也用這一步確認分享範圍。確認後才寫入團隊進度並啟動彙報。未確認的一般私聊留在原對話。

> 主責回覆「快好了」時，Assistant 保留原意或追問，不自行填成「完成 90%」。

#### 3.4.2 排程提醒

- **依設定發送。** 截止前提醒時間到達後，Assistant 私訊當時的主責。
- **停止條件。** 任務已完成／取消、等待組長處理來源權限，或該次提醒已發送時，不再送出。

#### 3.4.3 未回覆追問

1. **開始計時。** 進度詢問已送達後，才依設定計算未回覆時間。私訊失敗不計入。
2. **按設定再問。** 尚未收到回覆時，依追問間隔及次數上限處理。重試同一工作不增加追問次數。
3. **收到回覆就停止追問。** Assistant 收到可關聯至詢問的主責回覆後，立即記錄已回覆。資料不足時標為 `needs_clarification`，等待分享確認時標為 `awaiting_confirmation`。未確認內容不分享。
4. **結束本輪。** 新的共享進度結束本次詢問週期，下一輪依設定產生。

#### 3.4.4 組長彙報

- **彙報內容。** 可包含任務、最新已確認進度、詢問時間、未回覆或阻礙的依據及來源。
- **接收權限。** 組長只能收到有來源權限的項目，報告不得顯示被隱藏項目的數量或標題。
- **定期彙報。** 可按固定分鐘間隔、每日或每週。固定分鐘間隔從設定生效時間起算。
- **未回覆事件。** `no_response` 依獨立的彙報門檻觸發，追問次數和彙報門檻各自設定。

### 3.5 每日摘要

1. **選定摘要區間。** 每個來源分開處理。用兩次相鄰的排定時間定義 `[window_start, window_end)`，截止後的訊息進下一個區間。若設定改動，以生效時間切一次區間，之後按新時間計算，避免空隙或重疊。
2. **讀取成員訊息。** 只處理區間內有新成員訊息的來源。機器人／webhook 的自動輸出不計入。
3. **整理內容。** 摘要只使用同一來源的討論、決議、已公開待辦與未解問題。私人進度及跨來源風險評估留在各自的交付流程。一般聊天中的工作想法可列入摘要，正式建檔由組長明確指令或會議流程處理。
4. **在原來源發布。** 同一組 `(team_id, source_id, window_start, window_end)` 只發布一個正式版本。

- **讀取失敗或不完整。** 該來源標記待重試，保留原摘要區間。其他來源可繼續處理，待重試的來源不得記為「今日無新訊息」。

### 3.6 一般代為轉達

1. **組長提出請求。** Assistant 只在 `TeamLeader` 明確要求時啟動轉達。
2. **組長確認草稿。** Assistant 整理要傳的內容與接收對象，交給組長確認該版本。
3. **送前驗證。** Assistant 檢查接收對象的來源權限。若要把私人來源的內容送到頻道，必須能確認該頻道的受眾都有權取得。無法驗證時，請組長重新選擇合法的接收對象。
4. **發送。** 驗證通過後，依確認內容與接收對象發送，並標示「代組長轉達」。

- **重新確認。** 確認內容變更、收件人增加或來源範圍改變時，原確認失效。
- **交付限制。** 來源權限在組長確認後仍適用。Assistant 不自行更改收件名單或改成公開公告。

### 3.7 工具定義與呼叫

#### 3.7.1 工具定義（Function Tools）

Assistant 透過 Responses API 使用下列工具。每項函式定義包含英文名稱、用途及以 JSON Schema 描述的輸入欄位。

| ID | 工具 | 函式名稱 | 主要輸入 | 後端驗證與回傳 |
|---|---|---|---|---|
| TOOL01 | 提出團隊設定 | `draft_team_settings` | 組長的偏好訊息、目前設定版本（如有） | 依 [3.2](#32-初始化與設定) 驗證組長身分及設定欄位，回傳草稿版本或待補欄位。 |
| TOOL02 | 套用已確認的設定 | `apply_team_settings` | 草稿 ID、草稿版本、確認事件參照 | 驗證組長的確認及基準版本，回傳生效設定、版本與時間。 |
| TOOL03 | 整理會議 | `summarize_meeting` | 會議 ID、來源參照、文字訊息邊界 | 驗證會議範圍、結束事件及來源權限，回傳摘要、決議、任務候選與依據。 |
| TOOL04 | 建立待確認提案 | `create_task_proposal` | 任務候選、來源與尚待確認的資料 | 驗證來源與候選依據，回傳提案 ID 及待釐清事項。提案不啟動任務通知。 |
| TOOL05 | 正式指派任務 | `assign_task` | 組長明確指派的依據、工作、主責、期限，可附提案 ID 與協作者 | 驗證組長指派、必要欄位、成員資格及來源權限，回傳任務 ID 與通知啟用狀態。主責缺少來源權限時依 [3.3](#33-會議與任務建立) 暫停通知。 |
| TOOL06 | 異動任務 | `update_task` | 組長的異動請求、任務 ID、操作、新值及預期版本 | 驗證組長身分、狀態轉換及版本，回傳異動結果與版本。若影響排程，依新資料重算。 |
| TOOL07 | 記錄任務進度 | `record_task_progress` | 主責回報、任務 ID 或回覆關聯，提交時附草稿版本及確認事件參照 | 驗證主責身分、任務及分享確認。需釐清或確認時回傳對應狀態，確認後才寫入共享進度並依設定啟動彙報。 |
| TOOL08 | 查詢任務進度 | `get_task_progress` | 組長的查詢請求、任務 ID | 驗證組長身分與來源權限，回傳任務狀態、可分享進度及依據，或依 [2.5.3](#253-交付政策) 回傳可揭露的結果。 |
| TOOL09 | 向主責追問 | `request_task_followup` | 排程工作參照、任務 ID、原詢問 ID | 驗證排程授權、未回覆條件、版本與當前主責，回傳追問的排入狀態與詢問 ID。 |

#### 3.7.2 工具呼叫方式

| 方式 | 怎麼呼叫 | 官方文件 |
|---|---|---|
| 直接函式呼叫（Function Calling） | 模型提出函式名稱與參數，後端執行並回傳結果。 | [OpenAI 函式呼叫](https://developers.openai.com/zh-Hant/api/docs/guides/function-calling?api-mode=responses) |
| 程式化工具呼叫（Programmatic Tool Calling，PTC） | 模型可透過 OpenAI 代管的 JavaScript 執行環境組合多個工具。可用工具由 `allowed_callers` 指定，自訂函式仍由後端執行。 | [OpenAI 程式化工具呼叫](https://developers.openai.com/zh-Hant/api/docs/guides/tools-programmatic-tool-calling) |

1. **準備呼叫。** 後端依使用者、來源及工作範圍提供工具和資料。啟動時檢查選定模型是否支援程式化工具呼叫。
2. **驗證並執行。** 兩種方式共用後端的函式處理規則。後端從已驗證的事件與既有資料取得操作者、來源、確認及排程工作身分，再檢查參數、權限和版本。
3. **回傳結果。** 後端把範圍內可提供的結果回傳給 Responses API。若仍須真人確認或等 Discord 送達，按下節記錄狀態並結束本次呼叫。

#### 3.7.3 確認、重試與訊息送達

- **儲存紀錄。** 後端保存任務、排程、確認草稿及待送訊息紀錄（outbox），供後續工作繼續處理。
- **等真人確認。** 工具回傳 `awaiting_confirmation` 後結束呼叫。收到真人確認事件時另啟工作，驗證草稿、版本及確認人。
- **等訊息送出。** `queued` 表示訊息已排入 outbox。Discord 接受並回傳訊息 ID 後才標記 `sent`。
- **重試同一操作。** 寫入與發送操作使用去重鍵和版本檢查。同一操作已完成時，回傳原結果。需同時更新任務與 outbox 時，在同一筆資料庫交易內寫入。
- **查明送達結果。** Discord 發送結果不明時記為 `delivery_unknown`，先核對原次發送紀錄，確認可重送才處理。

## 4. 驗收

- 下表列出預定案例及預期結果，尚待實作後執行。
- **主流程。** 組長結束文字會議，Assistant 發布紀錄並建立已明確指派的任務。排程到點後，Assistant 私訊主責提醒或詢問。主責確認分享版本後，Assistant 依設定彙報給有來源權限的組長。
- **工具呼叫。** 依 [3.7](#37-工具定義與呼叫) 驗證直接函式呼叫與程式化工具呼叫各自的流程、權限檢查及重試結果。

| ID | 操作／條件 | 預期結果 |
|---|---|---|
| AC01 | 組長在文字會議中明確指定工作、主責與期限，並結束會議。 | `TOOL03` 整理會議，`TOOL05` 建立一筆來源可追溯的正式任務。Assistant 在原頻道發布紀錄，依設定啟動提醒。 |
| AC02 | 組員在會議中提出可能的主責，期限仍不明確。 | `TOOL04` 建立待確認提案。Assistant 請組長釐清，提案期間不啟動提醒。 |
| AC03 | 重送同一會議結束事件，或重試同一次工具呼叫。 | 同一筆指派及同一版會議紀錄各處理一次。 |
| AC04 | 正式指派的主責缺少來源權限。 | 保留任務並標為 `awaiting_leader_decision`。只私訊有權限的組長，暫停轉達及提醒。 |
| AC05 | 組長與主責都缺少來源權限。 | 兩人均收不到該來源內容，系統留下受限的內部待處理紀錄。 |
| AC06 | 組員在群聊問進度，未 @Assistant 也未送出指令。 | Assistant 保持安靜。 |
| AC07 | 成員在頻道 @Assistant 查詢，答案需使用其他有權來源。 | Assistant 在原處只提示改用私訊，驗權後私訊答案給提問者。 |
| AC08 | 組長缺少來源權限／Assistant 無法存取來源／查無資料。 | 能安全區分時，Assistant 回覆對應原因並隱去受限資訊。 |
| AC09 | 到達提醒時間，但目前在可發訊息時段外，或任務已完成。 | 有效工作延至下一個可發時段，已完成任務的提醒停止。 |
| AC10 | Discord 拒絕發送進度詢問私訊。 | 記為 `delivery_failed`，不改發公開訊息，也不計入未回覆。 |
| AC11 | 主責僅回報進度接近完成。 | Assistant 保留原意或追問，維持原任務狀態，不產生百分比。 |
| AC12 | 主責的回報混有私人內容。 | 草稿只給主責本人，`TOOL07` 在主責確認後才寫入共享版本。有來源權限的組長只收到該版本。 |
| AC13 | 協作者代主責回報，或主責要求直接改正式期限。 | `TOOL07` 不接受代報，`TOOL06` 不接受主責直接改期限。主責可向組長提出修改建議。 |
| AC14 | 進度詢問已送達，主責仍未回覆。 | 依設定追問／彙報。彙報說明進度未知並附上詢問依據。 |
| AC15 | 摘要區間內只有 Assistant 的摘要與提醒。 | 該來源不產生新的每日摘要。 |
| AC16 | 摘要截止後收到新訊息，本次摘要同時重試。 | 新訊息進下一個區間。本次維持原區間，最多發布一次。 |
| AC17 | 每日摘要讀取某個頻道時失敗。 | 該頻道保留原區間待重試。其他可處理的頻道繼續整理。 |
| AC18 | 原指派訊息被編輯／刪除。 | 保留正式任務、必要依據及原來源限制。 |
| AC19 | 組長改期限或更換主責，舊提醒同時啟動。 | 執行前的版本檢查判定舊工作失效，依新資料重算排程。 |
| AC20 | 轉達草稿確認後，內容或收件人又變動。 | 需請組長重新確認新版本，完成送前驗權後才發送。 |
| AC21 | 直接呼叫／程式化呼叫嘗試提供偽造的操作者、來源、確認或排程工作。 | 後端以可信事件和既有紀錄驗證，拒絕該請求，沒有越權讀取、寫入或發送。 |
| AC22 | 同一團隊的兩名成員有不同的來源權限。 | 兩人的檢索資料、模型上下文及程式化呼叫的執行上下文各自隔離。 |
| AC23 | 答案產生後、送出前，接收者失去來源權限。 | 送出前再次驗權並攔截答案。 |
| AC24 | 直接呼叫／已授權的程式化呼叫在操作寫入後逾時，後端重試同一操作。 | 兩種方式都回傳原操作結果。任務、outbox 及已送訊息均無重複。 |
| AC25 | 主責已回覆，但仍待釐清或確認分享草稿。 | 停止未回覆計時，記錄待釐清或待確認狀態。共享進度等主責確認後才寫入。 |
| AC26 | 成員可讀主頻道，但缺少私人討論串的存取權限。 | Assistant 不為該成員取得或交付討論串內容，主頻道的摘要也不納入該討論串。 |

## 5. 待決定

- **開發與部署。** 程式語言、資料庫、Discord SDK、部署平台。
- **模型。** OpenAI 模型及其 ID，選定後驗證是否支援程式化工具呼叫。
- **操作參數。** Discord 指令名稱、工具處理逾時、重試上限、每頁筆數。
- **整合測量。** 依實際使用流程量測效能與 API 費用。
