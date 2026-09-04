/* timeago.js — render <time data-ts="<iso>"> as human-readable local time.
 *
 * Server templates emit a raw-ish fallback inside the element so a no-JS or
 * pre-hydration render still shows something readable rather than a full ISO
 * timestamp with microseconds. This script replaces that text once loaded.
 *
 * TWO kinds of value arrive here, and they must not be confused:
 *
 *   - an INSTANT -- "2026-09-03T12:25:58.509212+00:00" (a proposal's
 *     created_at, a session's started_at). Carries a clock, so "5 minutes
 *     ago" is a claim the data supports.
 *   - a DAY -- "2026-09-03" (created_at in the markdown frontmatter of ideas,
 *     tech-debt findings, contracts, the wiki-health snapshot). Carries NO
 *     clock at all.
 *
 * A day handed to Date.parse resolves to UTC midnight (ES spec: the date-only
 * form is UTC), which is how an idea created today came out as "14 hours ago"
 * -- exactly the time since that midnight, in a UTC+3 browser. So a day is
 * parsed as LOCAL midnight instead and compared in whole calendar days of the
 * viewer, never in hours. Guarded by scripts/smoke_timeago.js.
 *
 * Recent instants read better relatively ("2 hours ago"); distant ones do not
 * -- "183 days ago" is worse than a date. So it switches at one week, and a
 * day-precision value switches on the same boundary.
 *
 * Repaints every 60s, because a dashboard left open overnight should not still
 * claim something happened "2 minutes ago".
 */
(function () {
  if (window.__timeagoInit) return;
  window.__timeagoInit = true;

  var WEEK = 7 * 86400;
  var WEEK_DAYS = 7;
  var DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;

  function locale() {
    return document.documentElement.lang || "en";
  }

  /* "2026-09-03" -> local midnight of that day, or null if it is not a
     date-only value. Round-tripped through the Date rather than trusted: the
     constructor rolls "2026-02-31" over into March instead of refusing it,
     and a malformed frontmatter date should keep the server's own text. */
  function parseDay(iso) {
    var m = DATE_ONLY.exec(iso);
    if (!m) return null;
    var y = +m[1], mon = +m[2] - 1, day = +m[3];
    var d = new Date(y, mon, day);
    if (d.getFullYear() !== y || d.getMonth() !== mon || d.getDate() !== day)
      return null;
    return d;
  }

  /* Whole calendar days between two dates, in the viewer's zone. Compared
     midnight-to-midnight rather than by dividing a millisecond difference:
     "today at 23:30" and "yesterday at 00:30" are half a day apart either
     way, and only the calendar tells them apart. Rounding absorbs the 23h
     and 25h days that DST transitions produce. */
  function dayDelta(then, now) {
    var a = new Date(then.getFullYear(), then.getMonth(), then.getDate());
    var b = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    return Math.round((a - b) / 86400000);
  }

  function relative(value, unit) {
    return new Intl.RelativeTimeFormat(locale(), { numeric: "auto" })
      .format(value, unit);
  }

  /* Absolute date. `withTime` is false for a day-precision value -- printing
     a clock there would show a time nobody recorded. */
  function absolute(d, withTime) {
    var sameYear = d.getFullYear() === new Date().getFullYear();
    return new Intl.DateTimeFormat(locale(), {
      day: "numeric",
      month: "short",
      year: sameYear ? undefined : "numeric",
      hour: withTime ? "2-digit" : undefined,
      minute: withTime ? "2-digit" : undefined,
    }).format(d);
  }

  function human(iso) {
    var day = parseDay(iso);
    if (day) {
      var days = dayDelta(day, new Date());
      // numeric:"auto" turns 0 and -1 into "today" / "yesterday".
      if (Math.abs(days) < WEEK_DAYS) return relative(days, "day");
      return absolute(day, false);
    }

    var then = Date.parse(iso);
    if (isNaN(then)) return null;
    var d = new Date(then);
    var secs = Math.round((then - Date.now()) / 1000);
    var abs = Math.abs(secs);

    if (abs < WEEK) {
      if (abs < 60) return relative(Math.round(secs), "second");
      if (abs < 3600) return relative(Math.round(secs / 60), "minute");
      if (abs < 86400) return relative(Math.round(secs / 3600), "hour");
      return relative(Math.round(secs / 86400), "day");
    }
    return absolute(d, true);
  }

  function full(iso) {
    var day = parseDay(iso);
    if (day)
      return new Intl.DateTimeFormat(locale(), { dateStyle: "full" })
        .format(day);
    var then = Date.parse(iso);
    if (isNaN(then)) return iso;
    return new Intl.DateTimeFormat(locale(), {
      dateStyle: "full",
      timeStyle: "medium",
    }).format(new Date(then));
  }

  function paint() {
    document.querySelectorAll("time[data-ts]").forEach(function (el) {
      var iso = el.getAttribute("data-ts");
      if (!iso) return;
      var text = human(iso);
      if (text === null) return;   // unparseable — leave the server's fallback
      el.textContent = text;
      if (!el.getAttribute("title")) el.setAttribute("title", full(iso));
      if (!el.getAttribute("datetime")) el.setAttribute("datetime", iso);
    });
  }

  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", paint);
  else paint();

  setInterval(paint, 60000);
})();
