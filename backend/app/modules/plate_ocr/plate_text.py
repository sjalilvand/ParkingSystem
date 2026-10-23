"""ابزارهای متنی پلاک ایران — نرمال‌سازی، اعتبارسنجی، قالب‌بندی.

برگرفته از plate_all.py (پلاک‌خوان ایرانی v3) و هم‌ساز با app/shared/plate.py
(نگاشت حروف به لاتین برای ذخیره‌سازی در سیستم پارکینگ).

قالب پلاک ایران: ۲ رقم + ۱ حرف + ۳ رقم (+ ۲ رقم کد استان بعد از «ایران»)
مثال: ۱۲ ب ۳۴۵ ایران ۶۷
"""
import re

DIGITS = "0123456789"

# ۱۴ حرف رسمی روی پلاک‌های ایران (بر اساس استاندارد پلاک‌بندی)
OFFICIAL_LETTERS = "بجدسصطعقلمنوهی"
LETTERS = OFFICIAL_LETTERS

# allowlist OCR — کلاس‌های «بومی» مدل EasyOCR فارسی.
# ⚠️ اندازه‌گیری واقعی (اکتبر ۲۰۲۶، ۴ عکس خیابانی): مدل fa ارقام را به‌صورت
# ارقام عربی شرقی (٠-٩) با اطمینان ۰٫۵-۰٫۹۹ می‌خواند؛ اجبار ارقام لاتین در
# allowlist کلاس بومی را می‌بست → ارقام حذف یا با اطمینان ۰٫۱-۰٫۳ خوانده
# می‌شدند (نمونه: فقط «ق» از کل پلاک!). normalize() ارقام عربی/فارسی را از
# قبل به لاتین تبدیل می‌کند، پس خروجی مسیرهای بعدی تغییری نمی‌کند.
OCR_ALLOWLIST = "٠١٢٣٤٥٦٧٨٩" + "۰۱۲۳۴۵۶۷۸۹" + OFFICIAL_LETTERS

# allowlist فقط-رقم برای خوانش متمرکز کادر «ایران» (کد استان) — همان کلاس‌های
# بومی مدل fa بدون حروف؛ کلمهٔ «ایران» در این حالت یا حذف می‌شود یا با اطمینان
# پایین خوانده می‌شود و در فیلتر بعدی کنار می‌رود.
OCR_PROVINCE_ALLOWLIST = "٠١٢٣٤٥٦٧٨٩" + "۰۱۲۳۴۵۶۷۸۹"

# کدهای رسمی دومرحله‌ای استان‌ها (ویکی‌پدیای فارسی: «پلاک وسایل نقلیه در ایران»،
# بازبینی اکتبر ۲۰۲۶) — پیش‌آگاه اعتبار: خوانشی که کد رسمی نباشد ضریب می‌گیرد.
# تهران ۱۱،۲۱،۲۲،۳۳،۳۸،۴۴،۵۵،۶۶،۷۷،۷۸،۸۸،۹۹،۱۰،۲۰،۳۰،۴۰،۵۰،۶۰،۷۰ |
# خراسان رضوی ۱۲،۳۲،۳۶،۴۲،۷۴ | اصفهان ۱۳،۲۳،۴۳،۵۳،۶۷ | فارس ۶۳،۷۳،۸۳،۹۳ |
# مازندران ۶۲،۷۲،۸۲،۹۲ | خوزستان ۱۴،۲۴،۳۴ | آذشرقی ۱۵،۲۵،۳۵ | آذغربی ۱۷،۲۷،۳۷ |
# کرمان ۴۵،۶۵،۷۵ | گیلان ۴۶،۵۶،۷۶ | همدان ۱۸،۲۸ | کرمانشاه ۱۹،۲۹،۳۹ |
# مرکزی ۴۷،۵۷ | بوشهر ۴۸،۵۸ | یزد ۵۴،۶۴ | کردستان ۵۱،۶۱ | گلستان ۵۹،۶۹ |
# چهارمحال ۷۱،۸۱ | قزوین ۷۹،۸۹ | هرمزگان ۸۴،۹۴ | سیستان ۸۵،۹۵ | سمنان ۸۶،۹۶ |
# زنجان ۸۷،۹۷ | قم ۱۶ | اردبیل ۹۱ | کهگیلویه ۴۹ | ایلام ۹۸ | خ‌شمالی ۲۶ |
# خ‌جنوبی ۳۲،۴۲،۵۲ | البرز ۲۱،۳۰،۳۸،۶۸،۷۸
PROVINCE_CODES = frozenset(
    "10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 "
    "30 31 32 33 34 35 36 37 38 39 40 41 42 43 44 45 46 47 48 49 "
    "50 51 52 53 54 55 56 57 58 59 60 61 62 63 64 65 66 67 68 69 "
    "70 71 72 73 74 75 76 77 78 79 81 82 83 84 85 86 87 88 89 "
    "91 92 93 94 95 96 97 98 99".split()
)

# دوقلوهای بصری ارقام در اندازهٔ ریز — فقط جفت‌های تأییدشده در آزمایش واقعی:
# عکس پژو (۲۹د۷۲۸ ایران ۶۳ فارس): ۶ → «۴» خوانده شد؛ خانوادهٔ ۲/۳ هم در
# همان تصویر دیده شد. برای هر چیز دیگری حدس نمی‌زنیم.
_PROV_CONFUSIONS = {"6": "4", "4": "6", "2": "3", "3": "2", "5": "0", "0": "5"}

_P2E = {ord(p): str(d) for d, p in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_AR2E = {ord(a): str(d) for d, a in enumerate("٠١٢٣٤٥٦٧٨٩")}
_ARABIC_FIX = str.maketrans({"ك": "ک", "ي": "ی", "ى": "ی", "ھ": "ه", "ﻻ": "لا"})

PLATE_RE = re.compile(rf"^(\d{{2}})([{LETTERS}])(\d{{3}})(?:IR)?(\d{{2}})?$")

# نگاشت "شباهت بصری" رقم→حرف (فقط حروف رسمی) — وقتی OCR حرف وسط را رقم خوانده.
# توجه: این نگاشت هیوریستیک است؛ کاندیدای حاصل با ضریب اطمینان کمتر رتبه می‌شود.
_VIS_DIGIT_TO_LETTER = {
    "0": "ه", "1": "ل", "2": "ب", "3": "ع", "4": "ه",
    # ٥ و د دوقلوی بصری‌اند — دو آزمایش واقعی: «د» پلاک به‌صورت «٥» خوانده شد
    "5": "د", "6": "ط", "7": "ن", "8": "ه", "9": "ق",
}

# حروف پرتکرار پلاک ایران (به‌ترتیب فراوانی) — برای بازسازی حرف وسط وقتی OCR
# آن را رقم خوانده است (مثال واقعی: «ب» → «۸» و متن ۷ نویسه‌ای نامعتبر).
_PRIOR_LETTERS = "بسلمهطقنو"

REPAIR_DEL_CONF = 0.85      # ضریب اطمینان کاندیدای حاصل از حذف نویسهٔ اضافه
REPAIR_LETTER_CONF = 0.60   # ضریب اطمینان کاندیدای حاصل از جایگزینی حرف
# ۰٫۸۵ — اندازه‌گیری اکتبر ۲۰۲۶ روی ۵ عکس واقعی: مدل fa گروه‌های عدد را به‌طور
# «سیستماتیک» راست‌به‌چپ می‌خواند («545س38» به‌جای «38س545» با اطمینان ۰٫۹۷).
# این خطای اتصال RTL/LTR است نه حدس — همهٔ ارقام سالم‌اند و فقط مرز گروه‌ها
# جابه‌جا شده. ضریب ۰٫۴۵ خوانشِ درستِ ۰٫۹۷ را به ۰٫۴۴ سرکوب می‌کرد و زیر
# آستانهٔ UI (۲۵٪) می‌برد → «صفر کاندیدا» یا کاندیدای زبالهٔ رأی‌خورده در رتبهٔ اول.
REPAIR_SWAP_CONF = 0.85     # ضریب کاندیدای جابه‌جایی گروه‌های عدد (اتصال LTR/RTL)
REPAIR_INSERT_CONF = 0.30   # ضریب کاندیدای درجِ رقمِ جای‌افتاده (خوانش ۵ نویسه‌ای)


def repair_candidates(text: str) -> list[tuple[str, float]]:
    """تولید کاندیداهای ترمیم‌شده برای متن‌های با طول غیراستاندارد (مثلاً ۷ نویسه).

    سناریوی رایج: حرف وسط پلاک رقم خوانده شده («ب»→«۸») + یک نویسهٔ اضافه
    (پیچ/مهر/کد استان چسبیده). برای هر حذفِ تک‌نویسه:
      * اگر نتیجه مستقیماً قالب معتبر بود → کاندیدا با اطمینان بالا؛
      * وگرنه اگر الگو «۲رقم + رقم + ۳رقم» بود، جایگاه ۲ با حروف پرتکرار
        ساخته می‌شود (هر حرف یک کاندیدا).

    برای متن‌های ۶ نویسه‌ای با الگوی آینه‌ای «۳رقم + حرف + ۲رقم» (خطای اتصال
    قطعات RTL/LTR — مثال واقعی: «۵۶۹ب۸۴» به‌جای «۱۴ب۵۹۱» نوع اتصال) گروه‌های
    عدد جابه‌جا می‌شوند: «۸۴ب۵۶۹».

    برمی‌گرداند [(متن_ترمیم_شده, ضریب_اطمینان), ...] — همهٔ خروجی‌ها قالب معتبر دارند.
    """
    t = normalize(text)
    out: list[tuple[str, float]] = []
    if len(t) == 7:
        seen: set[str] = set()
        # ترتیب حذف از مرکز به بیرون — نویسهٔ اضافه (پیچ/مهر/کد چسبیده) به‌ندرت
        # نخستین نویسه است؛ حذف‌های مرکزی احتمال بیشتری دارند و در امتیاز برابر،
        # زودتر تولیدشده‌ها در رتبه بالا می‌مانند (مرتب‌سازی پایدار).
        order = sorted(range(len(t)), key=lambda i: abs(i - (len(t) - 1) / 2))
        for i in order:
            s = t[:i] + t[i + 1:]
            if s in seen:
                continue
            seen.add(s)
            n, valid = validate(s)
            if valid:
                out.append((n, REPAIR_DEL_CONF))
                continue
            if len(s) == 6 and s[:2].isdigit() and s[2].isdigit() and s[3:].isdigit():
                for L in _PRIOR_LETTERS:
                    out.append((s[:2] + L + s[3:], REPAIR_LETTER_CONF))
            elif len(s) == 6 and s[:3].isdigit() and s[3] in LETTERS and s[4:].isdigit():
                # الگوی آینه‌ای پس از حذف از ۷ نویسه (خوانش واقعی ۲.jfif:
                # «٥٤٥س٣٨» → حذف رقم اضافه → «۵۴۵س۳۸» → جابه‌جایی → «۳۸س۵۴۵»)
                swapped = s[4:] + s[3] + s[:3]
                if swapped not in seen:
                    seen.add(swapped)
                    n2, valid2 = validate(swapped)
                    if valid2:
                        out.append((n2, REPAIR_SWAP_CONF))
    elif len(t) == 6:
        # الگوی آینه‌ای: ۳رقم + حرف + ۲رقم → جابه‌جایی گروه‌ها (خطای اتصال قطعات)
        if t[:3].isdigit() and t[3] in LETTERS and t[4:].isdigit():
            swapped = t[4:] + t[3] + t[:3]
            n, valid = validate(swapped)
            if valid:
                out.append((n, REPAIR_SWAP_CONF))
    elif len(t) == 5:
        # یک رقم جا افتاده (الگوی واقعی ۴.jpg: «11ق11» به‌جای «11ق111» — CRAFT
        # ارقام تکراری مجاور را ادغام می‌کند). برای هر جای درج و هر رقم:
        # فقط ترکیب‌هایی که قالب معتبر شوند («11قd11»/«11ق1d1»/«11ق11d») کاندیدا
        # می‌شوند — سقف ۳۰ کاندیدا با ضریب ۰٫۳۰؛ رتبه‌بندی موتور بقیهٔ کار را
        # می‌کند. حرفِ وسط دست‌نخورده می‌ماند (برخلاف حدسِ حرف، این‌جا حرف
        # از قبل درست خوانده شده و فقط یک رقم گم است).
        if any(ch in LETTERS for ch in t) and sum(ch.isdigit() for ch in t) == 4:
            seen5: set[str] = set()
            for i in range(len(t) + 1):
                for d in DIGITS:
                    s = t[:i] + d + t[i:]
                    if s in seen5:
                        continue
                    seen5.add(s)
                    n5, valid5 = validate(s)
                    if valid5:
                        out.append((n5, REPAIR_INSERT_CONF))
    # ادغام تکراری‌ها — مسیرهای حذف مختلف می‌توانند همان متن را بسازند
    # (مثل «۴۲۲۵۱۱۱»: حذف رقم دوم و سوم هر دو «۴۲۵۱۱۱» می‌دهند)؛ رأی‌شماری
    # موتور تکرار را «تأیید خوانش مستقل» می‌داند و امتیاز ساختگی می‌سازد
    merged: dict[str, float] = {}
    for txt, cf in out:
        if txt not in merged or merged[txt] < cf:
            merged[txt] = cf
    return sorted(merged.items(), key=lambda kv: -kv[1])


def normalize(text: str) -> str:
    """تبدیل ارقام فارسی/عربی به لاتین + حذف کلمه ایران + حذف نویسه‌های غیر پلاکی."""
    t = (text or "").translate(_P2E).translate(_AR2E).translate(_ARABIC_FIX)
    # کلمه «ایران» بخشی از پلاک است، نه نویسه پلاک — قبل از پاکسازی حذف شود
    t = t.replace("ایران", " ").replace("IRAN", " ").replace("Iran", " ")
    return re.sub(rf"[^\d{LETTERS}]", "", t)


def validate(text: str) -> tuple[str, bool]:
    """برمی‌گرداند (متن نرمال‌شده، معتبر بودن قالب پلاک ایران)."""
    t = normalize(text)
    return t, bool(PLATE_RE.match(t))


def format_plate(t: str) -> str:
    """قالب خوانا برای نمایش: 12B345 → «۱۲ ب ۳۴۵» (نمایش RTL در UI انجام می‌شود)."""
    t = normalize(t)
    if len(t) == 6:
        return f"{t[:2]} {t[2]} {t[3:]}"
    if len(t) == 8:
        return f"{t[:2]} {t[2]} {t[3:6]} | {t[6:]}"
    return t


def enforce_format(text: str) -> str:
    """نزدیک‌کردن متن خام OCR به قالب قانونی پلاک.

    ⚠️ نگاشت lossy است — فقط وقتی استفاده شود که اطمینان پایین و متن نامعتبر است.
    موقعیت ۲ (حرف) و بقیه ارقام بر اساس قالب ۶/۸ نویسه‌ای تصحیح می‌شوند.
    """
    t = normalize(text)
    if len(t) not in (6, 8):
        return t
    out = []
    for i, ch in enumerate(t):
        if i == 2:
            out.append(ch if ch in LETTERS else _VIS_DIGIT_TO_LETTER.get(ch, "ب"))
        else:
            out.append(ch if ch.isdigit() else "0")
    return "".join(out)


def assemble_from_pieces(pieces: list[tuple[float, str, float]]) -> list[tuple[str, float]]:
    """الحاقیه §۳ — اسمبلر ساخت‌یافته: ساخت کاندیدای پلاک از قطعات OCR.

    الهام از beam search مقید به فرمت (plate_all.py): قطعات متنی خوانده‌شده
    (با مختصات x) زیرمجموعه‌سازی و در دو ترتیب LTR/RTL به هم می‌چسبند و هر
    ترکیبی که بتوان آن را به قالب ایران «۲رقم + حرف + ۳رقم (+۲رقم استان)»
    رساند، کاندیدای معتبر است.

    امتیازدهی: کمینهٔ اطمینان قطعات؛ ضریب‌ها:
      * استفاده از قطعات بیشتر → ×(۱ + ۰٫۰۶×(r−۱))
      * داشتن کد استان (۸ نویسه) → +۰٫۱۰
      * متنِ از قبل قالب‌معتبر → ×۱٫۰؛ متنِ enforce‌شده (حرفِ حدس‌زده‌شده) → ×۰٫۸
      * تک‌قطعه (r=۱) → ×۰٫۸۵ (قطعهٔ واحدِ چسبیدهٔ «مقی + استان» کم‌اتکاست)

    pieces: [(x, text, conf), ...]  →  [(متن_نرمال_فارسی, امتیاز), ...]
    """
    from itertools import combinations

    out: dict[str, float] = {}
    toks = []
    for x, t, c in pieces:
        nt = normalize(t)
        if nt:
            toks.append((float(x), nt, float(c)))
    if not toks:
        return []
    for r in range(1, min(4, len(toks)) + 1):
        for combo in combinations(toks, r):
            for seq in (combo, tuple(reversed(combo))):
                s = "".join(t for _, t, _ in seq)
                if not (6 <= len(s) <= 8):
                    continue
                min_conf = min(c for _, _, c in seq)
                for s2 in ({s, enforce_format(s)} if len(s) in (6, 8) else {s}):
                    n, valid = validate(s2)
                    if not valid:
                        continue
                    score = min_conf * (1.0 + 0.06 * (r - 1))
                    if len(n) == 8:
                        score += 0.10
                    if s2 != s:            # حرف وسط حدس‌زده‌شده (enforce)
                        score *= 0.80
                    if r == 1:             # قطعهٔ واحد چسبیده — کم‌اتکاتر
                        score *= 0.85
                    if n not in out or out[n] < score:
                        out[n] = round(min(0.99, score), 4)
                # الحاقیه §۳ — متن‌های ۷ نویسه‌ای (اتصال ناقص قطعات): مسیر ترمیم
                # (حذف تک‌نویسه/ساخت حرف) با ضریب کاهشی — پوشش «۷۳۹۴۳۴۰» و امثال آن
                if len(s) == 7:
                    for fixed, mul in repair_candidates(s):
                        n2, valid2 = validate(fixed)
                        if not valid2:
                            continue
                        score2 = min_conf * (1.0 + 0.06 * (r - 1)) * 0.75 * mul
                        if n2 not in out or out[n2] < score2:
                            out[n2] = round(min(0.99, score2), 4)
    return sorted(out.items(), key=lambda kv: -kv[1])


def to_system_normalized(plate_fa: str, letter_mapping: str | None = None) -> str | None:
    """تبدیل پلاک فارسیِ نرمال‌شده (مثل «12ب345» یا «12ب34567») به فرمت سیستم.

    از app/shared/plate.py استفاده می‌کند → خروجی مثل «12B345» یا «12B345IR67».
    با این فرمت می‌توان مستقیماً vehicles.plate_normalized را جستجو کرد.
    """
    if not plate_fa:
        return None
    t = normalize(plate_fa)
    if len(t) == 8:
        raw = f"{t[:2]} {t[2]} {t[3:6]} ایران {t[6:]}"
    elif len(t) == 6:
        raw = f"{t[:2]} {t[2]} {t[3:]}"
    else:
        return None
    try:
        from app.shared.plate import normalize_plate
        return normalize_plate(raw, letter_mapping=letter_mapping)
    except Exception:
        return None
