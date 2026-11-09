"""Benchmark dataset: gold sentences + seeded typo injection (so the exact intended edits are known).

NOTE: Darija gold sentences were written without native review - have a native speaker check
them before treating Darija scores as final."""
import random
import re

GOLD = {
    "ar": [
        "كنت غادي نمشي للمدرسة ولكن الطوبيس تعطل",
        "واش نتا كاتعرف فين كاين المحطة ديال القطار؟",
        "صيفط ليا الفاتورة لمحمد العلوي على mohamed@example.ma قبل نهار الجمعة",
        "عيط ليا على 0612345678 ملي توصل للدار البيضاء",
        "غادي نتلاقاو غدا فالمقهى حدا الجامعة",
        "المعلم قال ليا خاصني نكمل الخدمة قبل العشية",
        "بغيت نشري طونوبيل جديدة ولكن الثمن غالي بزاف",
        "الجو اليوم زوين بزاف وبغينا نخرجو للشاطئ",
        "ماشي مشكل، غادي نصيفط ليك الملف دابا",
        "فين نقدر نلقى شي مطعم مزيان فمراكش؟",
        "خويا كيخدم فشركة كبيرة فالرباط",
        "ماقدرتش نجي البارح حيت كنت مريض",
        "شحال ديال الوقت خاصنا باش نوصلو لطنجة؟",
        "الاجتماع ديال غدا تأجل لنهار الاثنين",
        "عافاك، عاود ليا الشرح حيت ما فهمتش مزيان",
        "دابا غادي نخرج، كنتسناك برا",
        "كاين شي حل لهاد المشكل ديال الانترنت؟",
        "المرة الجاية غادي نجيب معايا صحابي",
        "هاد الكتاب زوين بزاف، نصحتك تقراه",
        "الطبيب قال ليا خاصني نرتاح جوج أيام",
        "بغيت نحجز بلاصة فالطيارة لباريس",
        "سير عاونو شوية، هو محتاج المساعدة",
        "المطر طاح بزاف البارح فالليل",
        "باقي ما كملتش الواجب ديالي",
        "جي عندي للدار نشربو الأتاي",
        "شكرا بزاف على المساعدة ديالك",
        "فاتورة الضو جات غالية هاد الشهر",
        "واش ممكن تفهمني كيفاش كيخدم هاد البرنامج؟",
        "كنت كنفكر نبدل الخدمة السنة الجاية",
        "صيفط ليا رقم التيليفون ديالك على sara.bennani@gmail.com",
        "غادي نوصل للمطار على جوج ديال العشية",
        "الدراري مشاو للمدرسة بكري اليوم",
        "ما عنديش الوقت باش نجاوبك دابا",
        "كاين مشكل فالحساب البنكي ديالي، عيطو ليا على +212 661 23 45 67",
        "غادي نقرا هاد الكتاب فالعطلة",
        "هاد الطاكسي غالي بزاف عليا",
        "بغيت نعرف واش الخدمة مازال كاينة",
        "الحمد لله، كلشي مزيان",
        "دابا كنتسنى الجواب ديالكم",
        "هاد الأسبوع كنت مشغول بزاف بالخدمة",
        "نهار الجمعة غادي نمشيو نصليو فالمسجد",
        "كنت فالسوق ولقيت ثمن الخضرة غالي",
    ],
    "en": [
        "Please send the report to Sarah Connor before Friday.",
        "I have an appointment tomorrow with Marie Curie at 3 pm.",
        "Could you call me back on +33 6 12 34 56 78 when you arrive?",
        "The meeting with Acme has been moved to next Monday.",
        "I would like to book a table for four people tonight.",
        "Thank you for your help, I really appreciate it.",
        "Our new office in Casablanca opens in January.",
        "Please confirm that you received my email at john.doe@acme.com.",
        "We are going to the beach this weekend if the weather is nice.",
        "She told me that the invoice was already paid.",
        "Can you explain how this program works?",
        "I forgot my password and I cannot log in to my account.",
        "The train to Paris leaves at half past six.",
        "He has been working on this project for three months.",
    ],
    "fr": [
        "Bonjour Karim, je vous envoie le contrat de Acme avant vendredi.",
        "Je suis allé à Casablanca hier avec Fatima, elle m'a dit qu'il faisait beau.",
        "Pouvez-vous me rappeler au 06 12 34 56 78 dès que possible ?",
        "La réunion avec le client a été reportée à lundi prochain.",
        "J'aimerais réserver une table pour quatre personnes ce soir.",
        "Merci beaucoup pour votre aide, je l'apprécie vraiment.",
        "Notre nouveau bureau à Rabat ouvrira en janvier.",
        "Veuillez confirmer la réception de mon message à marie.dupont@acme.fr.",
        "Nous irons à la plage ce week-end s'il fait beau.",
        "Elle m'a dit que la facture était déjà payée.",
        "Pouvez-vous m'expliquer comment fonctionne ce logiciel ?",
        "J'ai oublié mon mot de passe et je ne peux plus me connecter.",
        "Le train pour Paris part à six heures et demie.",
        "Il travaille sur ce projet depuis trois mois.",
    ],
}

_ACCENTS = str.maketrans("éèêàâùûôîç", "eeeaauuoic")


def _typo(word: str, lang: str, rng: random.Random) -> str:
    ops = []
    if lang == "ar" and word.endswith("ة"):
        ops.append(lambda w: w[:-1] + "ه")
    if lang == "fr" and word.translate(_ACCENTS) != word:
        ops.append(lambda w: w.translate(_ACCENTS))
    i = rng.randrange(1, len(word) - 1)
    ops += [lambda w: w[:i] + w[i + 1:],                  # deletion
            lambda w: w[:i] + w[i] + w[i:],               # duplication
            lambda w: w[:i] + w[i + 1] + w[i] + w[i + 2:]]  # swap
    return rng.choice(ops)(word)


def make_input(gold: str, lang: str, seed: int) -> str:
    rng = random.Random(seed)
    chunks = re.split(r"(\s+)", gold)
    cands = [k for k, c in enumerate(chunks)
             if "@" not in c and re.fullmatch(r"[^\W\d_]{4,}", c.rstrip("?.,!؟،"))
             and not (lang != "ar" and c[0].isupper())]
    for k in rng.sample(cands, min(2, len(cands))):
        core = chunks[k].rstrip("?.,!؟،"); tail = chunks[k][len(core):]
        new = _typo(core, lang, rng)
        if new != core:
            chunks[k] = new + tail
    return "".join(chunks)


def samples():
    out = []
    for lang, golds in GOLD.items():
        for n, g in enumerate(golds):
            inp = make_input(g, lang, seed=1000 * (len(lang) + n) + n)
            if inp != g:
                out.append((lang, inp, g))
    return out
