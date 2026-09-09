-- Enquiry intake store.
--
-- One row per accepted submission. This file is the whole database: there is no
-- migration framework, because the shape below is fixed by what henley-utils
-- reads and Salesforce stores, and changing it means changing those too.
--
-- Read by henley-utils' nightly update_salesforce_leads job, opened read-only.
-- Written only by the receiver.

CREATE TABLE IF NOT EXISTS enquiries (
  -- AUTOINCREMENT, not a bare INTEGER PRIMARY KEY. A bare rowid primary key
  -- reuses the ids of deleted rows; AUTOINCREMENT tracks a high-water mark in
  -- sqlite_sequence and never does. That matters more than usual here: the id
  -- is the Salesforce external key WebFormID_c__c, so a reused id does not
  -- create a duplicate — it silently overwrites an unrelated Lead.
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,

  -- Naive UTC, 'YYYY-MM-DD HH:MM:SS'. Exactly the format the WordPress
  -- wp_gf_entry.date_created column had, because henley-utils'
  -- _convert_date_to_brisbane() parses precisely that with strptime and
  -- attaches UTC. Storing ISO-8601, or SQLite's 'localtime', would either
  -- silently fall through that parser as an unconverted string or shift every
  -- enquiry by ten hours.
  created_at         TEXT    NOT NULL DEFAULT (datetime('now')),

  name               TEXT    NOT NULL,
  email              TEXT    NOT NULL,
  phone              TEXT,

  -- "How did you hear about us?" — kept as a column, no longer asked. The form
  -- dropped it (docs/decisions.md, "Enquiry form fields"): free text, unread by
  -- the classifier, and attribution that GA4 and the Ads tags already measure
  -- better. The column stays so the 9-tuple henley-utils reads keeps its shape
  -- and the question can come back without a schema change; the receiver still
  -- stores a value if one is posted.
  referral_source    TEXT,

  -- The two "How can we help?" checkboxes, stored as flags. The reader turns
  -- them back into the exact strings Gravity Forms stored — 'Apartment Living'
  -- and 'Private Aged Care' — which end up joined into Salesforce's
  -- InterestType_c__c. On a service page the form pre-ticks the matching box
  -- from the page the visitor is on, so the question is usually already
  -- answered by the time they see it.
  interest_apartment INTEGER NOT NULL DEFAULT 0,
  interest_aged_care INTEGER NOT NULL DEFAULT 0,

  enquiry_text       TEXT,

  -- Operational context. Not sent to Salesforce; kept for abuse triage and for
  -- knowing which page an enquiry came from.
  remote_ip          TEXT,
  user_agent         TEXT,
  page_path          TEXT
);

-- The nightly reader takes a 7-day window over created_at.
CREATE INDEX IF NOT EXISTS enquiries_created_at ON enquiries (created_at);

-- Start ids at 100000.
--
-- henley-utils de-duplicates against the *full set* of ids it has already
-- processed in data/forms.db — not a high-water mark — and that set currently
-- holds 1674..5229 from the WordPress era. A store starting at 1 would hand
-- back ids that are already in it: every early enquiry would be silently
-- skipped as "already processed", and any that did get through would upsert
-- onto the Salesforce Lead belonging to a different person. Starting well
-- above the historical range removes both failures. No history is migrated.
--
-- sqlite_sequence exists as soon as an AUTOINCREMENT table does, but carries
-- no row for a table until its first insert; seeding the row here means the
-- first real enquiry is 100000 rather than 1.
INSERT INTO sqlite_sequence (name, seq)
SELECT 'enquiries', 99999
WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = 'enquiries');
