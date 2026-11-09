import os

# Never read the developer's real config in tests.
os.environ["ELEGANT_PARROT_CONFIG"] = "/nonexistent/elegant-parrot-test.toml"
for _v in ("CORRECTOR_BACKEND", "OLLAMA_MODEL", "USE_NER"):
    os.environ.pop(_v, None)
