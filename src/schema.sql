PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- =========================
-- 1) 카테고리 (동적)
-- =========================
CREATE TABLE IF NOT EXISTS categories (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id    INTEGER NOT NULL,
  name        TEXT    NOT NULL,
  is_active   INTEGER NOT NULL DEFAULT 1,   -- 1=활성, 0=비활성
  sort_order  INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT    NOT NULL,
  updated_at  TEXT    NOT NULL,
  UNIQUE (guild_id, name)
);

CREATE INDEX IF NOT EXISTS idx_categories_guild_active
ON categories(guild_id, is_active, sort_order, name);

-- =========================
-- 2) 품목 (현재 재고)
--   - "삭제" = 비활성화(보관)
--   - 비활성 품목을 동일 이름/코드로 만들려 하면 "재활성화"로 처리 (Repo 로직)
--   - 보관 위치는 자유 텍스트
-- =========================
CREATE TABLE IF NOT EXISTS items (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id        INTEGER NOT NULL,
  category_id     INTEGER NOT NULL,

  name            TEXT    NOT NULL,             -- 품목명(검색 대상)
  code            TEXT,                         -- 코드(선택값, 검색 대상) 예: 49, G15
  qty             INTEGER NOT NULL DEFAULT 0,   -- 음수 허용
  warn_below      INTEGER NOT NULL DEFAULT 0,   -- 0이면 경고 끔
  note            TEXT    NOT NULL DEFAULT '',

  storage_location TEXT   NOT NULL DEFAULT '',  -- 보관 위치(자유 텍스트)

  is_active       INTEGER NOT NULL DEFAULT 1,   -- 1=활성, 0=비활성(보관)
  deactivated_at  TEXT,                         -- 보관 처리 시각(KST 텍스트, 선택)

  created_at      TEXT    NOT NULL,
  updated_at      TEXT    NOT NULL,

  UNIQUE (guild_id, name),
  UNIQUE (guild_id, code),                      -- code가 NULL이면 중복 허용(SQLite 특성)
  FOREIGN KEY(category_id) REFERENCES categories(id)
);

CREATE INDEX IF NOT EXISTS idx_items_guild_active
ON items(guild_id, is_active, name);

CREATE INDEX IF NOT EXISTS idx_items_guild_category
ON items(guild_id, category_id, name);

CREATE INDEX IF NOT EXISTS idx_items_guild_name
ON items(guild_id, name);

CREATE INDEX IF NOT EXISTS idx_items_guild_code
ON items(guild_id, code);

-- =========================
-- 3) 원장/로그 (모든 이벤트)
--  - 재고보고서: IN/OUT/ADJUST만 필터링
--  - 로그기록: 전 action 전부 포함
-- =========================
CREATE TABLE IF NOT EXISTS movements (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id                INTEGER NOT NULL,

  -- 품목 관련 이벤트가 아닐 수도 있으므로 NULL 허용
  item_id                 INTEGER,
  item_name_snapshot      TEXT    NOT NULL DEFAULT '',
  item_code_snapshot      TEXT    NOT NULL DEFAULT '',
  category_name_snapshot  TEXT    NOT NULL DEFAULT '',
  image_url       TEXT    NOT NULL DEFAULT '',  -- 품목 대표 이미지(디스코드 첨부 URL)


  action                 TEXT    NOT NULL,

  -- 재고 변동용 수량 값(관리 이벤트는 0)
  qty_change             INTEGER NOT NULL DEFAULT 0,   -- 내부 계산용(사용자에게는 노출 X)
  before_qty             INTEGER NOT NULL DEFAULT 0,
  after_qty              INTEGER NOT NULL DEFAULT 0,

  reason                 TEXT    NOT NULL DEFAULT '',

  success                INTEGER NOT NULL DEFAULT 1,   -- 1/0
  error_message          TEXT    NOT NULL DEFAULT '',

  -- 수행자
  discord_name           TEXT    NOT NULL,             -- 닉네임/표시이름 스냅샷(필수)
  discord_id             INTEGER,                      -- 디스코드 유저 ID(추적용, 저장 추천)

  -- 시간
  created_at_kst_text    TEXT    NOT NULL,             -- YYYY/MM/DD HH:MM:SS
  created_at_epoch       INTEGER NOT NULL,             -- seconds

  FOREIGN KEY(item_id) REFERENCES items(id)
);

CREATE INDEX IF NOT EXISTS idx_movements_guild_epoch
ON movements(guild_id, created_at_epoch DESC);

CREATE INDEX IF NOT EXISTS idx_movements_item_epoch
ON movements(item_id, created_at_epoch DESC);

CREATE INDEX IF NOT EXISTS idx_movements_guild_action_epoch
ON movements(guild_id, action, created_at_epoch DESC);

-- =========================
-- 4) 경고 알림 상태(도배 방지)
-- =========================
CREATE TABLE IF NOT EXISTS alert_state (
  guild_id           INTEGER NOT NULL,
  item_id            INTEGER NOT NULL,
  last_alert_epoch   INTEGER,
  last_alert_qty     INTEGER,
  muted_until_epoch  INTEGER,
  PRIMARY KEY (guild_id, item_id),
  FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
);

-- =========================
-- 5) 설정(채널/리포트/주기/대시보드 앵커)
-- =========================
CREATE TABLE IF NOT EXISTS settings (
  guild_id                  INTEGER PRIMARY KEY,

  -- 채널/대시보드
  dashboard_channel_id       INTEGER,  -- 재고관리 채널
  dashboard_message_id       INTEGER,
  alert_channel_id           INTEGER,  -- 재고_알림(경고)
  report_channel_id          INTEGER,  -- 재고_알림(엑셀 업로드)
  bot_admin_role_id          INTEGER,  -- 봇관리자 역할 ID(대표가 지정)
  search_mode                TEXT DEFAULT 'modal', -- 검색모드 기본(모달)

  -- 기본값/쿨다운
  default_warn_below         INTEGER NOT NULL DEFAULT 0,
  alert_cooldown_minutes     INTEGER NOT NULL DEFAULT 180,

  -- 보고서 업로드 시간(KST)
  report_hour                INTEGER NOT NULL DEFAULT 18,
  report_minute              INTEGER NOT NULL DEFAULT 30,

  -- 공휴일에도 업로드(기본 ON)
  report_on_holidays         INTEGER NOT NULL DEFAULT 1, -- 1=올림, 0=스킵(향후 옵션)

  -- 중복 업로드 방지
  last_daily_report_date     TEXT,     -- YYYY-MM-DD (일일 재고 보고서)
  last_daily_log_date        TEXT,     -- YYYY-MM-DD (일일 로그 기록)
  last_monthly_report_ym     TEXT,     -- YYYY-MM (월간 재고 보고서)
  last_monthly_log_ym        TEXT,     -- YYYY-MM (월간 로그 기록)

  -- purge 기록
  last_purge_epoch           INTEGER
);

-- =========================
-- 6) 즐겨찾기(옵션)
-- =========================
CREATE TABLE IF NOT EXISTS favorites (
  guild_id   INTEGER NOT NULL,
  user_id    INTEGER NOT NULL,
  item_id    INTEGER NOT NULL,
  created_at TEXT    NOT NULL,
  PRIMARY KEY (guild_id, user_id, item_id),
  FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
);
