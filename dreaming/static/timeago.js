/* timeago.js — render <time data-ts="<iso>"> as human-readable local time.
 *
 * Server templates emit a raw-ish fallback inside the element so a no-JS or
 * pre-hydration render still shows something readable rather than a full ISO
 * timestamp with microseconds. This script replaces that text once loaded.
 *
 * Recent instants read better relatively ("2 hours ago"); distant ones do not
 * -- "183 days ago" is worse than a date. So it switches at one week.
 *
 * Repaints every 60s, because a dashboard left open overnight should not still
 * claim something happened "2 minutes ago".
 */
(function () {
  if (window.__timeagoInit) return;
  window.__timeagoInit = true;

  var WEEK = 7 * 86400;

  function locale() {
    return document.documentElement.lang || "en";
  }

  function human(iso) {
    var then = Date.parse(iso);
    if (isNaN(then)) return null;
    var d = new Date(then);
    var secs = Math.round((then - Date.now()) / 1000);
    var abs = Math.abs(secs);

    if (abs < WEEK) {
      var rtf = new Intl.RelativeTimeFormat(locale(), { numeric: "auto" });
      if (abs < 60) return rtf.format(Math.round(secs), "second");
      if (abs < 3600) return rtf.format(Math.round(secs / 60), "minute");
      if (abs < 86400) return rtf.format(Math.round(secs / 3600), "hour");
      return rtf.format(Math.round(secs / 86400), "day");
    }

    var sameYear = d.getFullYear() === new Date().getFullYear();
    return new Intl.DateTimeFormat(locale(), {
      day: "numeric",
      month: "short",
      year: sameYear ? undefined : "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(d);
  }

  function full(iso) {
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
