"""Rule-based detector for names, places and addresses in English, French and Darija
(Moroccan Arabic, Latin "arabizi" and Arabic script).

spaCy ships no Darija model and its small EN/FR models miss lowercase chat-style text, so this
detector adds three deterministic layers that run BEFORE the statistical NER:

  1. cues      "my name is X", "je m'appelle X", "smiti X", "اسمي X", titles (Mme, Si, Lalla, السيد ...)
  2. gazetteer common Moroccan first names / surnames / cities (Latin + Arabic script)
  3. addresses "zenqa 12 hay X", "rue Hassan II", "شارع محمد الخامس"

It is heuristic: extend the word lists with `extra_names` / `extra_places` for your own data."""
from __future__ import annotations

import re
from typing import Iterable

from .detectors import Span

_AR = r"\u0600-\u06FF"
_CAP = r"A-ZÀ-ÖØ-Þ"
_LAT = r"[\w'\u2019-]"

_FIRST_LAT = """Mohamed Mohammed Muhammad Mohamad Ahmed Ahmad Youssef Yousef Youssouf Omar Amine Hamza Anas Ayoub Ayyoub Karim
Rachid Hicham Khalid Khaled Said Saïd Mehdi Mahdi Reda Rida Zakaria Zakariae Soufiane Sofiane Ismail Ismaïl Bilal Walid
Adil Abdelilah Abdelhak Abderrahim Abderrahmane Abdellah Abdelkader Abdelaziz Abdessamad Abdelmajid Brahim Ibrahim Hassan
Hassane Hocine Houssine Driss Idriss Jamal Kamal Mustapha Mostafa Nabil Nadir Noureddine Othmane Oussama Redouane Tarik
Taha Yassine Yacine Younes Zouhair Badr Ilyas Ilyass Ayman Marouane Mourad Naoufal Fouad Hamid Hafid Lahcen Lhoussaine
Fatima Fatiha Fatimazahra Khadija Khadidja Aicha Aïcha Amina Asmae Asmaa Btissam Bouchra Hajar Hanane Houda Imane Ikram
Kenza Lamia Latifa Laila Layla Loubna Malika Meryem Mariam Mouna Najat Naima Nadia Nezha Nour Rajae Rim Safae Salma Samira
Sanaa Soukaina Souad Wafae Yasmine Zineb Zahra Ghita Hind Hasnaa Khawla Maryam Oumaima Sara Sarah Siham Widad Zhor""".split()
_LAST_LAT = """Alaoui Benali Bennani Idrissi Tazi Fassi Berrada Chraibi Lahlou Benjelloun Benkirane Bensouda Amrani Zniber Ouazzani
Sqalli Kettani Slaoui Mernissi Skalli Lamrani Cherkaoui Filali Ghazouani Haddad Mansouri Naciri Rifai Saidi Tahiri
Zahraoui Benslimane Boukhari Bouazza Daoudi Bakkali Hajji Jabri Lazrak Hamdaoui Belhaj Harrak Kabbaj Kadiri Karimi
Lahrichi Najjar Ouali Rharbi Sebti Tounsi Yacoubi Zaki Zaidi Benmoussa Bouzid Chafik Elmaleh Guessous Lyoubi Tber Sbai
Bouhaddou Lamghari Ouahbi Radi Raji Sefrioui Squalli Tadlaoui Tlemcani Zerouali Alami Bouanani Belkhayat Berrechid""".split()
_CITIES_LAT = ["Casablanca", "Dar Lbida", "Dar El Beida", "Dar Elbeida", "Casa", "Rabat", "Fès", "Fes", "Fez", "Marrakech",
               "Marrakesh", "Tanger", "Tangier", "Agadir", "Oujda", "Tétouan", "Tetouan", "Meknès", "Meknes", "Kénitra",
               "Kenitra", "Salé", "Temara", "Témara", "Mohammedia", "El Jadida", "Eljadida", "Safi", "Nador", "Béni Mellal",
               "Beni Mellal", "Khouribga", "Settat", "Larache", "Essaouira", "Ouarzazate", "Dakhla", "Laâyoune", "Laayoune",
               "Taza", "Berkane", "Errachidia", "Ifrane", "Chefchaouen", "Al Hoceima", "Guelmim", "Tiznit", "Taroudant",
               "Azrou", "Khemisset", "Berrechid", "Skhirat", "Benguerir", "Dar Bouazza", "Sidi Maarouf", "Maarif", "Ain Sebaa",
               "Hay Riad", "Agdal", "Gauthier", "Oulfa"]
_FIRST_AR = """محمد أحمد يوسف عمر أمين حمزة أنس أيوب كريم رشيد هشام خالد سعيد مهدي رضا زكرياء زكريا سفيان إسماعيل اسماعيل بلال
وليد عادل عبد إبراهيم ابراهيم حسن ادريس إدريس جمال كمال مصطفى نبيل عثمان أسامة طارق ياسين يونس بدر إلياس الياس أيمن مروان مراد
نوفل فؤاد حميد فاطمة خديجة عائشة أمينة أسماء بشرى هاجر حنان هدى إيمان كنزة لطيفة ليلى لبنى مليكة مريم منى نجاة نعيمة نادية نزهة
رجاء ريم سلمى سميرة سناء سكينة سعاد وفاء ياسمين زينب زهرة غيثة هند خولة أميمة سارة سهام""".split()
_LAST_AR = """العلوي بنعلي بناني الإدريسي الادريسي التازي الفاسي برادة الشرايبي لحلو بنجلون بنكيران العمراني السقلي الكتاني السلاوي
المرنيسي لمراني الشرقاوي الفيلالي المنصوري الناصري الودغيري بنسليمان الحجي الجابري الحداد السعيدي الطاهري الزاكي""".split()
_CITIES_AR = ["الدار البيضاء", "الرباط", "فاس", "مراكش", "طنجة", "أكادير", "وجدة", "تطوان", "مكناس", "القنيطرة", "سلا", "تمارة",
              "المحمدية", "الجديدة", "آسفي", "الناظور", "بني ملال", "خريبكة", "سطات", "العرائش", "الصويرة", "ورزازات",
              "الداخلة", "العيون", "تازة", "بركان", "الراشيدية", "إفران", "شفشاون", "الحسيمة", "كلميم", "تيزنيت", "تارودانت"]

# Words that end a name captured after a cue ("smiti Youssef w ana ساكن f Rabat").
_STOP_LAT = set("""li w o u men mn f fi dyal d kan ana nta nti howa hia tel tele email mail mobile and et ou or at from de la le
est is am are living live habite habit sakn skn sakna kansken kanskn kansakn khdam khdama khadam travaille work works
mon ma mes my mail courriel numero numéro num phone portable gsm cin rib iban""".split())
_STOP_AR = set("""و في ف من ديال لي أنا انا عندي كنسكن كنعيش ساكن ساكنة خدام خدامة رقم هاتفي الهاتف البريد يسكن تسكن كيسكن ساكنين يعيش تعيش كيعيش يشتغل تشتغل كيخدم حول حولت دفع دفعت""".split())
_PARTICLE_LAT = r"(?:(?:el|al|ait|aït|ben|bin|ibn|ou|bou|de|du|des|la|le|d')[ -]?)"
_PARTICLE_AR = r"(?:(?:بن|ابن|أيت|ايت|أبو|ابو|عبد)\s)"


def _alt(words: Iterable[str]) -> str:
    return "|".join(re.escape(w) for w in sorted(set(words), key=lambda w: (-len(w), w)))


# ---- cues: (compiled regex with a (?P<pii>...) group, script, capitalised-only?) ------------------
def _name_tail(cap_only: bool) -> str:
    if cap_only:
        return rf"(?P<pii>[{_CAP}]{_LAT}+(?:[ -]+(?:{_PARTICLE_LAT})?[{_CAP}]{_LAT}+){{0,3}})"
    return rf"(?P<pii>[^\W\d_]{_LAT}+(?:[ -]+[^\W\d_]{_LAT}+){{0,2}})"


_AR_TAIL = rf"(?P<pii>[{_AR}]+(?:\s+[{_AR}]+){{0,2}})"

_CUES: list[tuple[re.Pattern[str], str, str]] = [  # (pattern, script, language)
    # English: strong cues accept a lowercase name; weak ones ("I am") need a Capital or "I am tired" would match
    (re.compile(r"(?i:\b(?:my name is|my name's|call me|name:|named)\s+)" + _name_tail(False)), "lat", "en"),
    (re.compile(r"(?i:\b(?:i am|i'm|this is|signed|regards,?|sincerely,?|best,?)\s+)" + _name_tail(True)), "lat", "en"),
    (re.compile(r"\b(?:Mrs|Ms|Mr|Dr|Prof|Mister|Miss)\.?\s+" + _name_tail(True)), "lat", "en"),
    # French
    (re.compile(r"(?i:\b(?:je m'appelle|je me nomme|mon nom est|mon nom:|moi c'est|pr[ée]nom:|nom:)\s+)" + _name_tail(False)),
     "lat", "fr"),
    (re.compile(r"(?i:\b(?:je suis|c'est|cordialement,?|bien cordialement,?)\s+)" + _name_tail(True)), "lat", "fr"),
    (re.compile(r"\b(?:Mme|Mlle|Pr|Me|M|Monsieur|Madame|Mademoiselle|Ma\u00eetre|Docteur|Professeur)\.?\s+" + _name_tail(True)),
     "lat", "fr"),
    # Darija in Latin script: usually lowercase, so any word counts until a stop word
    (re.compile(r"(?i:\b(?:smiti|smyti|smiyti|smitti|smitek|ismi|esmi|ismi howa|smit)\s+)" + _name_tail(False)), "lat", "darija"),
    (re.compile(r"\b(?:Si|Sidi|Lalla|Moulay|Hajj|Hajja|Hadj|Hadja|Oustad|Ostad)\.?\s+" + _name_tail(True)), "lat", "darija"),
    # Darija in Arabic script
    (re.compile(rf"(?<![{_AR}])(?:اسمي|إسمي|سميتي|سميت|اسمه|اسمها|إسمه)\s+" + _AR_TAIL), "ar", "darija"),
    (re.compile(rf"(?<![{_AR}])(?:السيد|السيدة|الآنسة|للا|لالة|سي|سيدي|مولاي|الحاج|الحاجة|الأستاذ|الأستاذة|الدكتور|الدكتورة|دكتور|"
                rf"مي)\s+" + _AR_TAIL), "ar", "darija"),
]

def _addr(words: str) -> "re.Pattern[str]":
    """'<street word> [n°] <number or Capitalised word> [up to 3 more]' - e.g. 'rue de la Paix 12', 'zenqa 12 hay Riad'."""
    return re.compile(
        rf"(?i:\b(?:{words})\b\.?)"
        rf"\s+(?:(?i:n°|no\.?|num|num[ée]ro|#)\s*)?(?:\d+[A-Za-z]?|[{_CAP}]{_LAT}*)"
        rf"(?:[ ]+(?:(?:de|du|des|la|le|el|al|d')[ ]+)?(?:\d+[A-Za-z]?|[{_CAP}]{_LAT}*)){{0,3}}")


_ADDR_FR = _addr(r"rue|avenue|av|bd|boulevard|quartier|cit[ée]|cite|r[ée]sidence|immeuble|imm|appartement|appt|apt|bloc|[ée]tage|etage|lotissement|lot")
_ADDR_DARIJA = _addr(r"zenqa|zanqa|zankat|derb|hay|lotissement|lot|r[ée]sidence|immeuble|imm|bloc")
_ADDR_AR = re.compile(rf"(?<![{_AR}])(?:شارع|زنقة|زنقت|درب|حي|إقامة|اقامة|عمارة|تجزئة|دوار)\s+[{_AR}\d]+(?:\s+[{_AR}\d]+){{0,3}}")

_NAME_LAT = re.compile(rf"(?<![\w])(?:{_PARTICLE_LAT})?(?:{_alt(_FIRST_LAT + _LAST_LAT)})(?![\w])", re.IGNORECASE)
_NAME_AR = re.compile(rf"(?<![{_AR}])(?:{_PARTICLE_AR})?(?:{_alt(_FIRST_AR + _LAST_AR)})(?![{_AR}])")
_CITY_LAT = re.compile(rf"(?<![\w])(?:{_alt(_CITIES_LAT)})(?![\w])", re.IGNORECASE)
_CITY_AR = re.compile(rf"(?<![{_AR}])(?:{_alt(_CITIES_AR)})(?![{_AR}])")


def _trim_at_stop(text: str, start: int, end: int, stops: set[str], arabic: bool = False) -> tuple[int, int]:
    """Cut a captured name before the first stop word."""
    out_end, n = start, 0
    words = list(re.finditer(r"\S+", text[start:end]))
    limit = 3 if arabic and any(w.group() == "عبد" for w in words[:2]) else (2 if arabic else 99)
    for m in words:
        w = m.group().lower().strip(",.;:!?\u060c")
        if w in stops or (arabic and w[:1] in "وفب" and w[1:] in stops) or n >= limit:
            break
        out_end, n = start + m.end(), n + 1
    return (start, out_end)


LANGUAGES = ("en", "fr", "darija")


class MoroccanDetector:
    """Names / places / addresses for EN + FR + Darija. `languages` switches each group on or off:
         en      English cues ("my name is X", Mr/Mrs/Dr)
         fr      French cues + French address words (rue, avenue ...)
         darija  Darija cues (Latin + Arabic script), Moroccan name/city gazetteer, zenqa/derb/hay addresses
       extra_names / extra_places are always active."""

    def __init__(self, extra_names: Iterable[str] = (), extra_places: Iterable[str] = (),
                 languages: Iterable[str] = LANGUAGES) -> None:
        self.languages = frozenset(languages)
        unknown = self.languages - set(LANGUAGES)
        if unknown:
            raise ValueError(f"unknown language(s) {sorted(unknown)}; choose from {list(LANGUAGES)}")
        self._extra_n = re.compile(rf"(?<![\w{_AR}])(?:{_alt(extra_names)})(?![\w{_AR}])", re.I) if extra_names else None
        self._extra_p = re.compile(rf"(?<![\w{_AR}])(?:{_alt(extra_places)})(?![\w{_AR}])", re.I) if extra_places else None

    def detect(self, text: str) -> list[Span]:
        L, out = self.languages, []
        for pat, script, lang in _CUES:
            if lang not in L:
                continue
            for m in pat.finditer(text):
                a, b = _trim_at_stop(text, m.start("pii"), m.end("pii"), _STOP_AR if script == "ar" else _STOP_LAT, script == "ar")
                if b > a:
                    out.append(Span(a, b, "PERSON"))
        if "fr" in L:
            out += [Span(m.start(), m.end(), "ADDRESS") for m in _ADDR_FR.finditer(text)]
        if "darija" in L:
            for pat in (_ADDR_DARIJA, _ADDR_AR):
                out += [Span(m.start(), m.end(), "ADDRESS") for m in pat.finditer(text)]
            # gazetteer: Latin names must be Capitalised (so "said", "nour" in normal prose are not flagged)
            for m in _NAME_LAT.finditer(text):
                if m.group().lstrip()[:1].isupper() or any(m.group().lower().endswith(x.lower()) for x in _LAST_LAT):
                    out.append(Span(m.start(), m.end(), "PERSON"))  # surnames are distinctive enough in any case
            out += [Span(m.start(), m.end(), "PERSON") for m in _NAME_AR.finditer(text)]
            out += [Span(m.start(), m.end(), "LOC") for m in _CITY_LAT.finditer(text) if m.group()[:1].isupper()]
            out += [Span(m.start(), m.end(), "LOC") for m in _CITY_AR.finditer(text)]
        if self._extra_n:
            out += [Span(m.start(), m.end(), "PERSON") for m in self._extra_n.finditer(text)]
        if self._extra_p:
            out += [Span(m.start(), m.end(), "LOC") for m in self._extra_p.finditer(text)]
        return _merge_adjacent_names(text, out)


def _merge_adjacent_names(text: str, spans: list[Span]) -> list[Span]:
    """'Youssef' + 'Alaoui' -> one PERSON span so the model sees one placeholder."""
    spans = sorted(spans, key=lambda s: (s.start, -s.end))
    out: list[Span] = []
    for s in spans:
        if out and s.start < out[-1].end:  # overlap: keep the longer
            if s.end > out[-1].end and s.kind == out[-1].kind:
                out[-1] = Span(out[-1].start, s.end, s.kind)
            continue
        if (out and s.kind == "PERSON" and out[-1].kind == "PERSON"
                and re.fullmatch(r"[ \-]+", text[out[-1].end:s.start])):
            out[-1] = Span(out[-1].start, s.end, "PERSON")
            continue
        out.append(s)
    return out
