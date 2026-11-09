# Trial Reel Agent (`jta_reels`)

Posts 4 Instagram trial reels a day, measures them at 6 h, 24 h, 48 h and 7 days, and learns
which topics and hooks win. Full spec: the "JTA Trial Reel Agent: Build Spec" Claude Doc (9 Nov 2026).

## Status: Week 1 (plumbing and proof)

| Piece | State |
|---|---|
| Database schema (all 12 tables + settings) | Built: `jta_reels/sql/001_init.sql`, `jta-reels db migrate` |
| Publisher (trial reels via the Instagram API) | Built and tested; waiting for the Meta token |
| Insights pull (6 h / 24 h / 48 h / 7 d) | Built and tested |
| Week 1 proof (`jta-reels probe`) | Built; run it once the token exists |
| Kill switch, run log, "fails twice, stops" | Built (`pause`, `resume`, `unstop`); Telegram send-only for now |
| Creator, gates, Analyst, Trend scout, Graduation watcher | Weeks 2 to 4 |
| Shorts renderer (sin-reel, Node) | Not in this repo yet: needs moving in (Week 1) |

## Decisions (9 Nov 2026)

- Slots in **US Eastern**: 08:00, 12:00, 16:00, 20:00 ET. Daylight saving is handled by the zone.
- Insights every 6 hours; each snapshot also stores the reel's real age.
- **Month 1 tests topic family and hook pattern only.** First frame (hook over action), length
  (45 to 60 s), voice (Paul) and caption style (statement) are held fixed. Slot and source are logged, not tested.
- Voice credits: run until they run out (under 5,000 characters), then remixes only.
- Graduation: MANUAL. Week 1 checks whether `is_shared_to_feed` flips when Matt graduates a reel.
- Bible quotes: **KJV**.

All of these live in the `settings` table (`jta-reels get test_plan`), not in code.

## Schedule (US Eastern)

| When (ET) | Bali | Job |
|---|---|---|
| every 10 min | | `jta-reels publish`: posts only when a slot is due (08:00, 12:00, 16:00, 20:00) |
| every 6 h | | `jta-reels insights` |
| 23:00 | 12:00 | Analyst scoring (Week 4) |
| 00:00 | 13:00 | Trend scout (later) |
| 01:00 | 14:00 | Creator builds 4 reels (Week 2), done well before 08:00 |
| Sun 23:00 | Mon 12:00 | Weekly playbook and digest (Week 4) |

The crontab is in `deploy/trial-reels.crontab`. It can run in any time zone: the code decides when a slot is due.

## How posting stays safe

- One publisher at a time (Postgres advisory lock). One live reel per slot (unique index). Daily cap of 4 per Eastern day.
- The container id is saved **before** publishing. If the network drops during publishing, the next run reads the
  container: `PUBLISHED` means it went out (the media id is found in recent posts, never posted again);
  `FINISHED` means it didn't (publish now).
- `media_publish` is never retried blindly. GET requests retry with backoff.
- Captions are checked in code before posting: no emojis, no em or en dashes, no "link in bio", at most 5 hashtags.
- `jta-reels pause` stops every job. A job that fails twice in a row stops and alerts; `jta-reels unstop <job>` restarts it.

## Setup for Matt (once)

**1. Instagram + Meta app**
1. JTA Instagram is a Business or Creator account, linked to the JTA Facebook Page.
2. developers.facebook.com: create an app (type Business). Add the Instagram product, "API setup with Facebook login".
3. Permissions: `instagram_basic`, `instagram_content_publish`, `instagram_manage_insights`,
   `pages_show_list`, `pages_read_engagement` (add `instagram_manage_comments` later for the Trend scout).
4. Meta Business Settings, Users, System users: add an admin system user, assign it the app, the Page
   and the Instagram account, then Generate token with the permissions above and expiry **Never**.
5. Find the Instagram user id:
   `curl "https://graph.facebook.com/v24.0/me/accounts?fields=name,instagram_business_account&access_token=TOKEN"`
6. Keep the app in development mode. It only posts to an account you own; confirm no app review is asked for.

**2. Cloudflare R2**: create a bucket (e.g. `jta-reels`) and an API token with Object Read & Write on that bucket only.

**3. Supabase**: create a project, click Connect and copy the **Session pooler** string (port 5432). Not the transaction pooler (6543); the direct string only works over IPv6.

**4. Server**: put the keys in `.env` (template: `.env.example`, never committed), then:

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/jta-reels db migrate
.venv/bin/jta-reels probe account
mkdir -p logs && crontab deploy/trial-reels.crontab
```

## Week 1 proof: run once, by hand

This settles the two open questions: does Meta report follows per reel, and can graduation be read through the API.

```bash
# 1. Post one real trial reel (an existing Short works; it only goes to non-followers)
jta-reels probe post --file short.mp4 --caption "The first lie he'll tell you.
Sin isn't what you think.
Follow for part 2
#jesus #faith #bible #sin #christian"

# 2. Snapshot every field and metric, one at a time
jta-reels probe read MEDIA_ID --label before

# 3. Graduate it in the Instagram app (share to followers), then:
jta-reels probe read MEDIA_ID --label after
jta-reels probe diff reels_probe/MEDIA_ID-before.json reels_probe/MEDIA_ID-after.json

# 4. After 48 hours, read again to see which metrics have numbers
jta-reels probe read MEDIA_ID --label 48h
```

Then:
- If `is_shared_to_feed` flipped to true: `jta-reels set graduation_signal '"is_shared_to_feed"'`.
  The watcher then sees graduations by itself instead of asking which ones you graduated.
- If `follows` is missing, nothing to do: the insights job records it and the score falls back to profile visits.
- If Meta rejects the container, the error text says why. The parameters are built from Meta's trial reels
  changelog; Meta's reference pages couldn't be read from the build machine, so this is the first live check.

## Week 1 results (9 Nov 2026)

Two trial reels posted from the cloud through the API, both remixes of existing Shorts with new hook cards:
001 Holy Spirit (media 18450994663123723) and 002 boat / why suffering (media 18144495985615612).

| Question | Answer |
|---|---|
| Does `trial_params` work through the API? | **Yes**, with graduation MANUAL, on the Facebook-login setup, with `share_to_feed` left out |
| Follows per reel? | **No.** `follows`, `profile_visits` and `profile_activity` all return "not supported for this media product type" |
| Metrics available per reel | views, reach, likes, comments, shares, saved, total_interactions, ig_reels_avg_watch_time, ig_reels_video_view_total_time, reels_skip_rate, reposts |
| Graduation visible? | Pending: `is_shared_to_feed` is false on both before graduation; re-read after Matt graduates one |
| ElevenLabs | 0 credits on 9 Nov, so the system starts in remix-only mode |

Snapshots are kept on the `trial-media` branch under `probe/`.

**Open decision:** the score's 30% follow component can't be measured per reel. Candidates: shares + saves per
1,000 views (both reported, both predict growth), or skip rate. Account-level follower change can be logged daily as context only.

## Tests

```bash
JTA_TEST_DATABASE_URL="postgresql://..." .venv/bin/python -m pytest tests/test_reels_*.py -v
```

Database tests use a throwaway schema per test and are skipped without `JTA_TEST_DATABASE_URL`.
They cover: posting into a due slot, one reel per slot, the daily cap, the network dropping before and
after Meta publishes (posted exactly once either way), container errors, blocked captions, the kill switch,
"fails twice, stops", the publisher lock, insights buckets, unsupported metrics, and graduation detection.
