"""Deterministic (no-LLM) success/kill-criteria suggestion lookup.

Cross-project evaluation item b.5 (deferred design session, 2026-07-24):
"system recommends, founder decides" (WORKING-RULES.md Sec.10) -- a
lightweight, editable, always-clearly-labeled-ESTIMATE starting point
for F1 (success_criteria) and F2 (kill_criteria), never an automatic
fill. Keyed by sector (a new, first-of-its-kind fixed taxonomy in this
project -- no sector field exists anywhere in the 32-field Dossier
schema, and Unicorn Hunter's own "sector" is itself free text) and a
market-size band (also new and founder-selected, never extracted from
B6's free-text research paragraph -- a real fixture example contains
three different, non-equivalent market-size figures in one field,
confirming regex extraction would be unreliable, not just risky).

Sector-primary, band-parameterized design: each sector has ONE success
template and ONE kill template containing a {timeframe} placeholder,
rather than a full sector x band content matrix (10 x 4 = 40 pairs) --
keeps authored content maintainable (14 strings total) while still
genuinely keyed by both dimensions.
"""

SECTOR_OPTIONS = [
    ("saas_software", "برمجيات وتقنية (SaaS)"),
    ("ecommerce_retail", "تجارة إلكترونية وتجزئة"),
    ("fintech", "تقنية مالية (Fintech)"),
    ("healthtech", "تقنية صحية (Healthtech)"),
    ("edtech", "تقنية تعليمية (Edtech)"),
    ("food_restaurant", "أغذية ومطاعم"),
    ("proptech_realestate", "عقارات وتقنية عقارية"),
    ("logistics_delivery", "لوجستيات وتوصيل"),
    ("content_media", "محتوى ووسائط"),
    ("general_other", "أخرى / عام"),
]

MARKET_SIZE_BAND_OPTIONS = [
    ("small", "صغير (سوق متخصص/محلي)"),
    ("medium", "متوسط (سوق إقليمي)"),
    ("large", "كبير (سوق عالمي/واسع)"),
    ("unknown", "غير معروف"),
]

DEFAULT_SECTOR_KEY = "general_other"
DEFAULT_BAND_KEY = "unknown"

_BAND_TIMEFRAMES = {
    "small": "خلال أول 3 أشهر",
    "medium": "خلال أول 6 أشهر",
    "large": "خلال أول 6-12 شهر",
    "unknown": "خلال الفترة الأولى التي تحددها",
}

_SECTOR_TEMPLATES = {
    "saas_software": {
        "success": "الوصول إلى عدد ملموس من المستخدمين النشطين الذين يدفعون اشتراكاً فعلياً {timeframe}، مع معدل احتفاظ (retention) معقول.",
        "kill": "عدم القدرة على تحويل أي مستخدم تجريبي إلى مشترك مدفوع {timeframe}.",
    },
    "ecommerce_retail": {
        "success": "تحقيق عدد مبيعات متكرر (عملاء يشترون أكثر من مرة) {timeframe} بهامش ربح إيجابي بعد التكاليف المباشرة.",
        "kill": "عدم تحقيق أي مبيعات متكررة، أو هامش ربح سالب باستمرار، {timeframe}.",
    },
    "fintech": {
        "success": "معالجة حجم معاملات حقيقي بثقة العملاء (وليس تجريبياً فقط) {timeframe}، مع الالتزام بأي متطلبات تنظيمية أساسية معروفة.",
        "kill": "عدم الحصول على أي عميل مستعد لربط بيانات مالية حقيقية بالمنتج {timeframe}، أو عائق تنظيمي يمنع التشغيل القانوني.",
    },
    "healthtech": {
        "success": "تبني فعلي من عدد ملموس من المستخدمين أو الجهات الصحية المستهدفة {timeframe}، مع عدم وجود عائق تنظيمي/سلامة يمنع الاستخدام.",
        "kill": "عدم القدرة على تجاوز الحد الأدنى من متطلبات السلامة/الامتثال، أو رفض واضح من الجهات الصحية المستهدفة، {timeframe}.",
    },
    "edtech": {
        "success": "إتمام عدد ملموس من المتعلمين لتجربة كاملة (وليس تسجيلاً فقط) مع مؤشر رضا إيجابي {timeframe}.",
        "kill": "معدل تسرب مرتفع جداً (لا يكمل المتعلمون التجربة) أو عدم استعداد أي جهة/فرد للدفع {timeframe}.",
    },
    "food_restaurant": {
        "success": "تحقيق عدد طلبات/زيارات متكررة بهامش ربح موجب بعد تكلفة المكونات والتشغيل المباشر {timeframe}.",
        "kill": "استمرار هامش ربح سالب بعد تغطية التكاليف المباشرة، أو عدم وجود عملاء متكررين، {timeframe}.",
    },
    "proptech_realestate": {
        "success": "إتمام عدد ملموس من الصفقات/الاتفاقيات الفعلية (وليس اهتماماً مبدئياً فقط) {timeframe}.",
        "kill": "عدم إتمام أي صفقة فعلية رغم وجود اهتمام مبدئي، {timeframe}.",
    },
    "logistics_delivery": {
        "success": "تنفيذ عدد ملموس من عمليات التوصيل/النقل بجودة مقبولة (التزام بالمواعيد) وبتكلفة تشغيل مستدامة {timeframe}.",
        "kill": "تكلفة تشغيل تفوق العائد بشكل مستمر، أو معدل فشل/تأخر مرتفع في التوصيل، {timeframe}.",
    },
    "content_media": {
        "success": "بناء قاعدة متابعين/مستخدمين فعليين متفاعلين (وليس أرقام مشاهدة سطحية فقط) {timeframe}، مع مؤشر أولي على إمكانية تحقيق دخل.",
        "kill": "عدم نمو أي تفاعل حقيقي رغم النشر المستمر {timeframe}.",
    },
    "general_other": {
        "success": "تحقيق أول مؤشر ملموس على أن عملاء حقيقيين يريدون هذا الحل ومستعدون للدفع أو الالتزام به {timeframe}.",
        "kill": "عدم وجود أي إشارة حقيقية على اهتمام العملاء أو استعدادهم للدفع {timeframe}.",
    },
}


def get_success_kill_criteria_suggestion(sector_key: str, band_key: str) -> dict:
    """Returns {"success_criteria": str, "kill_criteria": str, "sector_key": str, "band_key": str}.

    Unrecognized sector/band keys degrade to the safe defaults rather
    than raising -- defensive only (the fixed dropdowns feeding this
    should never actually produce an unrecognized key), costs nothing.
    """
    resolved_sector = sector_key if sector_key in _SECTOR_TEMPLATES else DEFAULT_SECTOR_KEY
    resolved_band = band_key if band_key in _BAND_TIMEFRAMES else DEFAULT_BAND_KEY

    template = _SECTOR_TEMPLATES[resolved_sector]
    timeframe = _BAND_TIMEFRAMES[resolved_band]

    return {
        "success_criteria": template["success"].format(timeframe=timeframe),
        "kill_criteria": template["kill"].format(timeframe=timeframe),
        "sector_key": resolved_sector,
        "band_key": resolved_band,
    }
