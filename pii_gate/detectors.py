"""Pluggable detectors. Anything with `detect(text) -> list[Span]` qualifies."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    kind: str  # uppercase letters only, e.g. EMAIL


class Detector(Protocol):
    def detect(self, text: str) -> list[Span]: ...


def _luhn(digits: str) -> bool:
    s, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        s += d
        alt = not alt
    return s % 10 == 0


DEFAULT_PATTERNS: dict[str, re.Pattern[str]] = {
    "EMAIL": re.compile(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"),
    "IBAN": re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,3})?\b"),
    "URL": re.compile(r"https?://[^\s<>\"']+"),
    "IP": re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"),
    "CARD": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}(?:\s?\d{2})?\b"),
    "PHONE": re.compile(r"(?<!\w)(?:\+|00)\d[\d .()-]{7,16}\d|(?<!\w)0\d(?:[ .-]?\d{2}){4}\b"),
    # Vehicle Identification Number: 17 chars, never I/O/Q, mixes letters and digits.
    "VIN": re.compile(r"\b(?=[A-HJ-NPR-Z0-9]*\d)(?=[A-HJ-NPR-Z0-9]*[A-Z])[A-HJ-NPR-Z0-9]{17}\b"),
    # Bank/customer account numbers: after a label (account, compte, RIB...) or long dashed digit groups.
    "ACCOUNT": re.compile(r"(?i:\b(?:account|acct|a/c|compte|rib)\b)[^\n\d]{0,15}(?P<pii>\d[\d -]{5,}\d)"
                          r"|\b\d{4}(?:-\d{4}){2,}\b|\b\d{3}[ ]?\d{3}[ ]?\d{16}[ ]?\d{2}\b"),
    # Amounts with a currency symbol or code (US/EU formats).
    "MONEY": re.compile(r"[$\u20ac\u00a3]\s?\d+(?:[, .]\d{3})*(?:[.,]\d{1,2})?"
                        r"|\b\d+(?:[, .]\d{3})*(?:[.,]\d{1,2})?\s?(?:EUR|USD|GBP|CHF|MAD|DH|DHS|dirhams?|euros?|dollars?|\u20ac)(?!\w)"),
    # Street addresses: "742 Evergreen Terrace", "12 bis rue de la Paix"; US "WA 98101" ZIP.
    "ADDRESS": re.compile(
        r"\b\d{1,5}\s+(?:[A-Z][\w'\u2019.-]*\s+){1,3}(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Terrace|Court|Ct|Way|Place|Pl|Square|Sq)\b"
        r"|\b\d{1,4}(?:\s?(?:bis|ter))?,?\s+(?:rue|avenue|av\.|boulevard|bd|chemin|all\u00e9e|impasse|place|quai|route)\s+(?:[\w\u00c0-\u00ff'\u2019-]+\s?){1,4}",
        re.IGNORECASE),
    # Moroccan identifiers: CIN (national ID card, 1-2 letters + 5-6 digits), ICE (15 digits, labelled).
    "CIN": re.compile(r"(?i:\b(?:cin|c\.i\.n|carte nationale)\b)[^\n\w]{0,6}(?P<pii>[A-Za-z]{1,2}\d{5,6})"
                      r"|(?<![\w])[A-Z]{1,2}\d{5,6}(?!\w)"),
    "ICE": re.compile(r"(?i:\bICE\b)[^\n\w]{0,6}(?P<pii>\d{15})"),
    "ZIP": re.compile(r"\b[A-Z]{2}\s\d{5}(?:-\d{4})?\b"),
}


class RegexDetector:
    """Structured identifiers. Pass `extra` to add project-specific patterns,
    or `patterns` to replace the defaults entirely."""

    def __init__(self, extra: Mapping[str, str | re.Pattern[str]] | None = None,
                 patterns: Mapping[str, re.Pattern[str]] | None = None) -> None:
        self.patterns: dict[str, re.Pattern[str]] = dict(DEFAULT_PATTERNS if patterns is None else patterns)
        for k, v in (extra or {}).items():
            self.patterns[k] = re.compile(v) if isinstance(v, str) else v
        for k in self.patterns:
            if not re.fullmatch(r"[A-Z]+", k):
                raise ValueError(f"kind {k!r} must be uppercase letters only")

    def detect(self, text: str) -> list[Span]:
        out = []
        for kind, pat in self.patterns.items():
            for m in pat.finditer(text):
                if kind == "CARD" and not _luhn(re.sub(r"\D", "", m.group())):
                    continue
                a, b = m.span("pii") if m.re.groupindex.get("pii") and m.group("pii") is not None else m.span()
                out.append(Span(a, b, kind))
        return out


# --- NER hygiene -----------------------------------------------------------------------------
# Small spaCy models (and running a French model on English text) tag lowercase words, verbs,
# sentence openers and product names as entities, and glue neighbouring words into one span.
# A real name/place/organisation is a run of Capitalised words, so we keep only those runs.
_PARTICLES = {"de", "du", "des", "del", "della", "di", "da", "van", "von", "der", "den", "la", "le", "el",
              "al", "bin", "ben", "ibn", "of", "the", "and", "&", "d'", "l'", "et", "y"}
_LABELS = {"CIN", "ICE", "DH", "IBAN", "SSN", "VIN", "ID", "IP", "URL", "PIN", "VAT", "SIRET", "BIC", "SWIFT", "RIB", "TVA",
           "NIR", "CVV", "OTP", "PDF", "FAQ", "OK", "USD", "EUR", "GBP", "PM", "AM"}
_PRODUCTS = {"zoom", "teams", "tesla", "model", "skype", "slack", "outlook", "excel", "word", "windows",
             "linux", "android", "iphone", "ipad", "google", "microsoft", "apple", "amazon", "whatsapp",
             "linkedin", "facebook", "twitter", "youtube", "gmail", "docker", "python", "java"}
_STOP = {w.lower() for w in """
Afterward Afterwards After Before During Last Next This That These Those Then There Here Today Tomorrow
Yesterday Tonight Now Soon Later Earlier Also Still Just Only Even However Therefore Meanwhile Moreover
Furthermore Finally First Second Third Please Thanks Thank Hello Hi Hey Dear Regards Best Sincerely
Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March    July
 September October November December Yes No Not But And Or So If When While Because Since
Although Though Unless Until Once Maybe Perhaps Sure Okay Note Notes See Please Let Can Could Would Should
 Shall  Might Must Our My Your His Her Its Their We You They He She It I In On At To From With
For By Of As An A The Is Are Was Were Be Been Do Does Did Have Has Had What Which Who Whom Whose How Why
Après Avant Pendant Dernier Prochain Ce Cet Cette Ces Alors Puis Ici Aujourd'hui Demain Hier Bientôt
Cependant Donc Pourtant Enfin Ensuite Bonjour Bonsoir Salut Merci Cordialement Lundi Mardi Mercredi Jeudi
Vendredi Samedi Dimanche Janvier Février Mars Avril Mai Juin Juillet Août Septembre Octobre Novembre
Décembre Oui Non Mais Et Ou Donc Or Ni Car Si Quand Comme Je Tu Il Elle Nous Vous Ils Elles On Le La Les
Un Une Des Du De Mon Ma Mes Ton Ta Tes Son Sa Ses Notre Nos Votre Vos Leur Leurs
Dr Mr Mrs Ms Prof Sir Miss Mister Mme Mlle Monsieur Madame Mademoiselle Docteur Professeur Maître Me
""".split()}
_WORD = re.compile(r"[^\W\d_][\w'\u2019.-]*|\d+")


def clean_ner_span(text: str, start: int, end: int, kind: str) -> list[Span]:
    """Split a raw NER span into runs of Capitalised words and drop junk (verbs, sentence openers,
    product names, field labels like 'SSN'). Returns zero or more cleaned spans."""
    seg = text[start:end]
    runs: list[list[re.Match[str]]] = []
    cur: list[re.Match[str]] = []
    pending: list[re.Match[str]] = []  # particles waiting for a capitalised word to follow
    for m in _WORD.finditer(seg):
        w = m.group()
        lw = w.lower().rstrip(".")
        if w[0].isupper() and lw not in _PRODUCTS and w not in _LABELS and not w.isdigit() \
                and (lw not in _STOP or lw in _PARTICLES):
            cur += pending + [m]
            pending = []
        elif cur and lw in _PARTICLES:
            pending.append(m)
        else:
            if cur:
                runs.append(cur)
            cur, pending = [], []
    if cur:
        runs.append(cur)
    out = []
    for run in runs:
        words = [m.group().lower().rstrip(".") for m in run]
        if len(run) == 1 and (words[0] in _STOP or words[0] in _PARTICLES or len(words[0]) < 2):
            continue
        out.append(Span(start + run[0].start(), start + run[-1].end(), kind))
    return out


_NER_MAP = {"PERSON": "PERSON", "LOCATION": "LOC", "ORGANIZATION": "ORG", "NRP": "NRP"}


class PresidioDetector:
    """NER via Presidio + spaCy, one or several languages (spans are merged by the composite).
    Requires `pip install elegant-parrot[ner]` plus a spaCy model per language."""

    def __init__(self, models: Mapping[str, str] | None = None, threshold: float = 0.5) -> None:
        from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        models = dict(models or {"en": "en_core_web_sm"})
        nlp = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": l, "model_name": m} for l, m in models.items()],
        }).create_engine()
        registry = RecognizerRegistry(supported_languages=list(models))
        registry.load_predefined_recognizers(languages=list(models), nlp_engine=nlp)
        self._a = AnalyzerEngine(nlp_engine=nlp, registry=registry, supported_languages=list(models))
        self._langs, self._thr = list(models), threshold

    def detect(self, text: str) -> list[Span]:
        out: list[Span] = []
        for lang in self._langs:
            res = self._a.analyze(text=text, language=lang, entities=list(_NER_MAP),
                                  score_threshold=self._thr)
            for r in res:
                out += clean_ner_span(text, r.start, r.end, _NER_MAP[r.entity_type])
        return out


class FilteredDetector:
    """Wrap any detector, keeping only kinds in `allow` (if given) and dropping kinds in `deny`."""

    def __init__(self, inner: Detector, allow: Sequence[str] | None = None, deny: Sequence[str] = ()) -> None:
        self.inner, self.allow, self.deny = inner, set(allow) if allow else None, set(deny)

    def detect(self, text: str) -> list[Span]:
        return [s for s in self.inner.detect(text)
                if s.kind not in self.deny and (self.allow is None or s.kind in self.allow)]


class CompositeDetector:
    """Runs several detectors; on overlap the EARLIER detector wins (so list precise ones,
    e.g. regex, before fuzzy NER), then the longer span."""

    def __init__(self, detectors: Sequence[Detector]) -> None:
        self.detectors = list(detectors)

    def detect(self, text: str) -> list[Span]:
        ranked = [(prio, s) for prio, d in enumerate(self.detectors) for s in d.detect(text)]
        out: list[Span] = []
        for _, s in sorted(ranked, key=lambda x: (x[0], -(x[1].end - x[1].start), x[1].start)):
            if all(s.end <= o.start or s.start >= o.end for o in out):
                out.append(s)
        return sorted(out, key=lambda s: s.start)


DEFAULT_NER_MODELS = {"en": "en_core_web_sm", "fr": "fr_core_news_sm"}


def default_detector(ner: bool = True, models: Mapping[str, str] | None = None) -> CompositeDetector:
    from .multilingual import MoroccanDetector

    ds: list[Detector] = [RegexDetector(), MoroccanDetector()]
    if ner:
        try:
            ds.append(PresidioDetector(models or DEFAULT_NER_MODELS))
        except Exception as exc:  # noqa: BLE001
            log.warning("NER unavailable (%s) - regex-only detection", exc)
    return CompositeDetector(ds)
