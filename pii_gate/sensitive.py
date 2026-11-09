"""GDPR Art. 9/10 special-category cues and re-identification (quasi-identifier) cues.

Used in the STRICT profile that is switched on whenever text may leave the machine (external backend):

  SensitiveDetector  health, religion, politics, trade union, sexual orientation, ethnicity,
                     biometric/genetic data, criminal records  (EN / FR / Darija Latin + Arabic script)
  QuasiDetector      job titles, "leads the X department", family relations - harmless alone, but
                     combined they single out one person (GDPR Recital 26)

Keyword based, so it is deliberately over-inclusive: a false positive costs a local-only fallback,
a false negative costs a leak. It cannot understand context - treat it as a safety net, not a proof."""
from __future__ import annotations

import re

from .detectors import Span

# Kinds that must never be sent to an external processor (GDPR Art. 9 and Art. 10).
SPECIAL_CATEGORY_KINDS = frozenset({"HEALTH", "RELIGION", "POLITICS", "UNION", "SEXUAL", "ETHNIC", "BIOMETRIC", "CRIMINAL"})

_LISTS: dict[str, str] = {
    "HEALTH": r"""multiple sclerosis|sclérose en plaques|scl[ée]rose|cancer\w*|tumou?r\w*|tumeur\w*|diab[eè]t\w*|hiv|vih|aids|sida
        |depress\w+|d[ée]pression|anxi[eé]t\w*|anxiety|[ée]pilep\w+|asthm\w+|alzheimer\w*|parkinson\w*|pregnan\w+|grossesse|enceinte
        |chimioth[ée]rapie|chemotherap\w+|radioth[ée]rapie|radiotherap\w+|dialys\w+|stroke|avc|autis\w+|adhd|bipolar\w*|schizophr\w+
        |covid\S*|medical|m[ée]dical\w*|treatments?|traitements?|therap\w+|th[ée]rapie\w*|diagnos\w+|surger\w+|chirurgi\w+|surgeon
        |medications?|m[ée]dicaments?|prescri\w+|ordonnance|sick leave|arr[êe]t maladie|disabilit\w+|handicap\w*|illness|disease
        |maladi\w+|patients?|psychiatr\w+|psycholog\w+|oncolog\w+
        |mard|mrid|marid|3ilaj|3lej|ilaj|tbib|tabib|kancer|sukar|مرض|مريض|علاج|طبيب|سرطان|سكري|اكتئاب
        |جراح\w*|دواء|أدوية|إعاقة|حمل""",
    "RELIGION": r"""muslim\w*|christian\w*|jewish|catholic\w*|buddhis\w*|hindu\w*|atheis\w+|religio\w+|church|mosque|synagogue|imam
        |priest|rabbi|ramadan|prayer\w*|musulman\w*|chr[ée]tien\w*|juif\w*|catholique\w*|[ée]glise|mosqu[ée]e|pri[èe]re|ramadhan
        |مسلم|مسيحي|يهودي|دين|مسجد|كنيسة|صلاة|الإسلام|رمضان""",
    "POLITICS": r"""political\w*|politic\w+|parti politique|party member|vot(?:e|ed|ing)\b|election\w*|[ée]lection\w*|حزب|سياس\w+|انتخابات""",
    "UNION": r"""trade union\w*|union member|syndicat\w*|syndical\w*|نقابة|نقابي""",
    "SEXUAL": r"""gay|lesbian\w*|bisexual\w*|transgender|lgbt\w*|homosexual\w*|sexual orientation|orientation sexuelle|homosexuel\w*|مثلي""",
    "ETHNIC": r"""ethnic\w*|racial\w*|origine ethnique|origine raciale|ethnie|عرق|أمازيغي""",
    "BIOMETRIC": r"""fingerprint\w*|biometric\w*|facial recognition|dna|genetic\w*|empreinte\w*|biom[ée]trique\w*|g[ée]n[ée]tique\w*|بصمة""",
    "CRIMINAL": r"""convict\w+|criminal record|arrested|imprison\w*|prison|casier judiciaire|condamn\w+|سجن|سوابق""",
}
_WB = r"(?<![\w])(?:{})(?![\w])"
_COMPILED = {k: re.compile(_WB.format(re.sub(r"\s*\n\s*", "", v)), re.IGNORECASE) for k, v in _LISTS.items()}


class SensitiveDetector:
    """Flags Art. 9/10 cue words and phrases; each hit becomes e.g. ⟦HEALTH_x⟧."""

    def detect(self, text: str) -> list[Span]:
        return [Span(m.start(), m.end(), kind) for kind, pat in _COMPILED.items() for m in pat.finditer(text)]


_MODS = r"(?:senior|junior|lead|principal|chief|head|deputy|assistant|associate|staff|global|regional|vice|group|general)"
_TITLE = (r"(?:architect|engineer|developer|manager|director|consultant|surgeon|physician|nurse|lawyer|attorney|teacher|professor|"
          r"analyst|officer|president|ceo|cto|cfo|coo|founder|partner|specialist|administrator|accountant|auditor|"
          r"directeur|directrice|responsable|ing[ée]nieur|chirurgien|m[ée]decin|avocat\w*|professeur|comptable|"
          r"مدير|مهندس|طبيب|محامي|أستاذ)")
_QUASI = {
    "ROLE": re.compile(
        rf"(?i:\b(?:{_MODS}\s+)*(?:[a-z]+\s+){{0,2}}?{_TITLE}\b)"
        r"|(?i:\b(?:leads?|heads?|manages?|directs?|runs?|dirige|g[èe]re|dirigeant|responsable de)\s+(?:the|le|la|l')?\s*"
        r"[\w\s-]{3,40}?\s(?:department|team|unit|division|service|d[ée]partement|[ée]quipe|p[ôo]le))"),
    "RELATION": re.compile(
        r"(?i:\b(?:his|her|their|my|our|your)\s+(?:sister|brother|wife|husband|son|daughter|mother|father|cousin|uncle|aunt|"
        r"partner|girlfriend|boyfriend|spouse|colleague|manager|boss)\b"
        r"|\b(?:sa|son|ma|mon|leur|notre)\s+(?:s[œo]eur|fr[èe]re|femme|mari|fils|fille|m[èe]re|p[èe]re|cousin\w*|oncle|tante|"
        r"conjoint\w*|coll[èe]gue|patron\w*)\b"
        r"|\b(?:khti|khouya|khoya|okht|mrati|rajli|mra dyali|wlidi|bnti|mami|baba)\b)"
        r"|(?<![\w\u0600-\u06FF])(?:أخته|أخوه|زوجته|زوجها|ابنه|بنته|أمه|أبوه|أختي|أخي|زوجتي|زوجي)(?![\w\u0600-\u06FF])"),
}


class QuasiDetector:
    """Indirect identifiers: job titles, department leadership, family relations."""

    def detect(self, text: str) -> list[Span]:
        return [Span(m.start(), m.end(), kind) for kind, pat in _QUASI.items() for m in pat.finditer(text)]
