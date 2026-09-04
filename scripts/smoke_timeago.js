/* smoke_timeago.js — проверка dreaming/static/timeago.js на настоящем файле.
 *
 *   node scripts/smoke_timeago.js
 *
 * Зачем отдельный харнесс: timeago.js кормят ДВА разных вида значений, и
 * перепутать их нельзя.
 *
 *   - момент времени: "2026-09-03T12:25:58.509499+00:00" (created_at заявок,
 *     started_at сессий) — тут «5 минут назад» честно;
 *   - только дата: "2026-09-03" (created_at во frontmatter идей, техдолга,
 *     контрактов) — часов в этом значении НЕТ.
 *
 * Date.parse по спеке ES трактует форму «только дата» как UTC-полночь, поэтому
 * идея, созданная сегодня, раньше показывалась как «14 часов назад» — ровно
 * столько прошло с UTC-полуночи. Тесты ниже фиксируют, что дневные значения
 * рендерятся с дневной точностью и в ЛОКАЛЬНОМ дне зрителя.
 *
 * Время «сейчас» подменяется, иначе граничные случаи (23:30 и 00:30) не
 * проверить: именно на них ломается наивный расчёт «разница в мс / 86400».
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SRC = path.join(__dirname, "..", "dreaming", "static", "timeago.js");
const code = fs.readFileSync(SRC, "utf8");

/** Элемент <time data-ts="..."> с тем же fallback-текстом, что кладёт шаблон. */
function makeEl(ts, fallback) {
  return {
    attrs: { "data-ts": ts },
    textContent: fallback === undefined ? ts : fallback,
    getAttribute(k) {
      return this.attrs[k] === undefined ? null : this.attrs[k];
    },
    setAttribute(k, v) {
      this.attrs[k] = v;
    },
  };
}

/** Локальная дата -> ms, чтобы пины «сейчас» читались в зоне зрителя. */
function localMs(y, m, d, hh, mm) {
  return new Date(y, m - 1, d, hh, mm, 0, 0).getTime();
}

/** Прогоняем НАСТОЯЩИЙ timeago.js с подменённым Date.now() и фейковым DOM. */
function paint(ts, { now, lang = "ru", fallback } = {}) {
  const el = makeEl(ts, fallback);
  const RealDate = Date;
  class FakeDate extends RealDate {
    constructor(...args) {
      if (args.length === 0) super(now);
      else super(...args);
    }
    static now() {
      return now;
    }
  }
  const sandbox = {
    window: {},
    setInterval() {},
    Date: FakeDate,
    document: {
      readyState: "complete",
      documentElement: { lang },
      querySelectorAll() {
        return [el];
      },
      addEventListener() {},
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox, { filename: SRC });
  return el;
}

function rel(value, unit, lang = "ru") {
  return new Intl.RelativeTimeFormat(lang, { numeric: "auto" }).format(value, unit);
}

let failed = 0;
function check(name, actual, expected) {
  const ok = typeof expected === "function"
    ? expected(actual)
    : actual === expected;
  if (!ok) {
    failed += 1;
    console.log(`FAIL  ${name}`);
    console.log(`      got:      ${JSON.stringify(actual)}`);
    console.log(`      expected: ${
      typeof expected === "function" ? "(predicate)" : JSON.stringify(expected)
    }`);
  } else {
    console.log(`ok    ${name}  ->  ${JSON.stringify(actual)}`);
  }
}

// Никаких часов — ни словом («14 часов назад»), ни циферблатом («20 авг., 03:00»):
// в дневном значении времени нет, выдумывать его нельзя.
const noHours = (s) =>
  !/час|hour|минут|minute|секунд|second/.test(s) && !/\d{1,2}:\d{2}/.test(s);

// ---- только дата: дневная точность, локальный день -----------------------

check(
  "дата сегодня, днём -> «сегодня» (был баг: «14 часов назад»)",
  paint("2026-09-03", { now: localMs(2026, 9, 3, 16, 39) }).textContent,
  rel(0, "day"),
);

check(
  "дата сегодня, поздний вечер -> всё ещё «сегодня»",
  paint("2026-09-03", { now: localMs(2026, 9, 3, 23, 30) }).textContent,
  rel(0, "day"),
);

check(
  "дата сегодня -> без часов/минут в тексте",
  paint("2026-09-03", { now: localMs(2026, 9, 3, 23, 30) }).textContent,
  noHours,
);

check(
  "вчерашняя дата в 00:30 -> «вчера», а не «сегодня»",
  paint("2026-09-02", { now: localMs(2026, 9, 3, 0, 30) }).textContent,
  rel(-1, "day"),
);

check(
  "дата 3 дня назад -> «3 дня назад»",
  paint("2026-08-31", { now: localMs(2026, 9, 3, 16, 39) }).textContent,
  rel(-3, "day"),
);

check(
  "дата старше недели -> абсолютная дата без времени",
  paint("2026-08-20", { now: localMs(2026, 9, 3, 16, 39) }).textContent,
  (s) => /20/.test(s) && /авг/i.test(s) && noHours(s),
);

check(
  "у дневного значения в title нет выдуманного времени",
  paint("2026-09-03", { now: localMs(2026, 9, 3, 16, 39) }).attrs.title,
  (s) => typeof s === "string" && s.length > 0 && !/00:00|0:00/.test(s),
);

check(
  "дата в будущем -> «завтра», а не «через N часов»",
  paint("2026-09-04", { now: localMs(2026, 9, 3, 16, 39) }).textContent,
  rel(1, "day"),
);

// ---- момент времени: прежнее поведение не тронуто ------------------------

check(
  "момент 5 минут назад -> «5 минут назад»",
  paint("2026-09-03T13:34:00+00:00", { now: localMs(2026, 9, 3, 16, 39) }).textContent,
  rel(-5, "minute"),
);

check(
  "момент 2 часа назад -> «2 часа назад»",
  paint("2026-09-03T11:39:00+00:00", { now: localMs(2026, 9, 3, 16, 39) }).textContent,
  rel(-2, "hour"),
);

check(
  "момент старше недели -> абсолютная дата СО временем",
  paint("2026-08-20T09:15:00+00:00", { now: localMs(2026, 9, 3, 16, 39) }).textContent,
  (s) => /авг/i.test(s) && /\d{2}:\d{2}/.test(s),
);

check(
  "en-локаль берётся из <html lang>",
  paint("2026-09-03", { now: localMs(2026, 9, 3, 16, 39), lang: "en" }).textContent,
  rel(0, "day", "en"),
);

// ---- мусор: серверный fallback остаётся как есть -------------------------

check(
  "непарсируемое значение -> текст сервера не тронут",
  paint("not-a-date", { now: localMs(2026, 9, 3, 16, 39), fallback: "not-a-date" }).textContent,
  "not-a-date",
);

check(
  "пустое значение -> текст сервера не тронут",
  paint("", { now: localMs(2026, 9, 3, 16, 39), fallback: "—" }).textContent,
  "—",
);

console.log(failed === 0 ? "\nALL OK" : `\n${failed} FAILED`);
process.exit(failed === 0 ? 0 : 1);
