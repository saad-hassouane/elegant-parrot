"""Benchmark correction models through the full PII pipeline.

    python scripts/bench_model.py MODEL [MODEL ...] [--retries 3] [--limit N]

Edit-level scoring (like ERRANT): word-token edits input->gold are the intended fixes;
edits input->output are what the model did.
  fix%       intended edits the model reproduced exactly
  unwanted   edits not in gold, per sample (over-editing / rewording)
  exact%     output == gold
  F0.5       precision-weighted F (unwanted edits penalised more than missed ones)
  fail%      calls where placeholders could not be restored (text left untouched)
The do-nothing baseline is printed for reference. --retries 1 = raw model reliability."""
import argparse, dataclasses, difflib, logging, re, statistics, sys, time
logging.disable(logging.CRITICAL)
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import bench_data
from corrector.config import Settings
from corrector.pipeline import Corrector

TOK = re.compile(r"\w+|[^\w\s]")


def edits(a: str, b: str) -> set:
    ta, tb = TOK.findall(a), TOK.findall(b)
    return {(i1, i2, tuple(tb[j1:j2]))
            for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes()
            if tag != "equal"}


def f05(tp, n_out, n_gold):
    p = tp / n_out if n_out else 1.0
    r = tp / n_gold if n_gold else 1.0
    return 0.0 if p + r == 0 else 1.25 * p * r / (0.25 * p + r)


def score(src, gold, out):
    eg, eo = edits(src, gold), edits(src, out)
    tp = len(eg & eo)
    return dict(fix=tp / len(eg) if eg else 1.0, unwanted=len(eo - eg), exact=out == gold,
                f=f05(tp, len(eo), len(eg)))


def report(name, lang, rows):
    m = lambda k: statistics.mean(r[k] for r in rows)
    print(f"{name:<15}{lang:<5}{len(rows):>4}{100*m('fix'):>7.0f}%{m('unwanted'):>9.2f}"
          f"{100*m('exact'):>7.0f}%{m('f'):>7.2f}{100*m('fail'):>7.0f}%{m('t'):>7.1f}")


ap = argparse.ArgumentParser()
ap.add_argument("models", nargs="+"); ap.add_argument("--retries", type=int, default=3)
ap.add_argument("--limit", type=int, default=0, help="max samples per language (0 = all)")
a = ap.parse_args()
data = bench_data.samples()
if a.limit:
    seen, keep = {}, []
    for s in data:
        seen[s[0]] = seen.get(s[0], 0) + 1
        if seen[s[0]] <= a.limit: keep.append(s)
    data = keep

print(f"{'model':<15}{'lang':<5}{'n':>4}{'fix':>8}{'unwant':>9}{'exact':>8}{'F0.5':>7}{'fail':>8}{'s/call':>7}")
report("do-nothing", "ALL", [{**score(s, g, s), "fail": 0, "t": 0} for _, s, g in data])
for model in a.models:
    c = Corrector(dataclasses.replace(Settings.load(), backend="local", retries=a.retries, ollama_model=model))
    c.provider.correct("warmup")
    rows = {}
    for lang, src, gold in data:
        t0 = time.time(); r = c.correct(src); dt = time.time() - t0
        rows.setdefault(lang, []).append({**score(src, gold, r.text), "fail": not r.ok, "t": dt})
    for lang in ("en", "fr", "ar"):
        if lang in rows: report(model, lang, rows[lang])
    report(model, "ALL", [r for v in rows.values() for r in v])
    sys.stdout.flush()
