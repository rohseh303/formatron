"""Token vocabularies for the benchmark: the synthetic one and real tokenizers.

Synthetic vocabulary
--------------------

The default is *not* a real model tokenizer.  It is a deterministic, hand-built
vocabulary of ~3-4k tokens: every single byte (so any byte string is
reachable), JSON punctuation with and without surrounding whitespace, numbers,
``true``/``false``/``null``, a few hundred common English words, the key names
used by the corpus, and common substrings (URL fragments, dates, UUID-ish
hex, escape sequences, a handful of multi-byte UTF-8 tokens).

Because it is synthetic, absolute per-token mask latencies are not comparable
with a real 32k-152k BPE vocabulary, and the random walk in the runner can
produce strings a language model never would.  The numbers are only meaningful
*relative* to each other (hardened vs default, engine vs engine, family vs
family).

Real tokenizer vocabulary (``--tokenizer``)
-------------------------------------------

``build_vocab_file`` loads a Hugging Face tokenizer **once in the parent
process**, builds the ``kbnf.Vocabulary`` exactly the way Formatron's
``create_engine_vocabulary`` does (byte-level BPE "Ġ"/"Ċ" mangling and
sentencepiece "▁" are undone by ``get_original_characters``), and pickles the
raw ``{id: bytes}`` / ``{id: str}`` maps.  ``kbnf.Vocabulary`` itself is not
picklable and ``import transformers`` costs ~20 s, so every spawned child
instead calls ``load_vocab_file`` (~20 ms) and ``kbnf_vocabulary_from_maps``
(~70 ms for 152k tokens).  The random walk decodes with the real token bytes.
"""

from __future__ import annotations

import datetime
import functools
import os
import pickle
import typing

EOS_TEXT = b"<|eos|>"
VOCAB_FILE_FORMAT = 1

_PUNCT = [
    b"{", b"}", b"[", b"]", b",", b":", b'"', b"\\", b"/",
    b'{"', b'"}', b'"]', b'"}]', b'"}}', b'"]}', b'":', b'": "', b'": ', b'":"',
    b'", "', b'","', b'"},{"', b'"}, {"', b'},{', b'}, {', b'],[', b'], [',
    b'"]}', b']}', b'}}', b']]', b'}]', b'[]', b'{}', b'[{', b'[[', b'{"a"',
    b'": [', b'": {', b'":[', b'":{', b': [', b': {', b', ', b',\n', b',\n  ',
    b',\n    ', b'{\n', b'{\n  ', b'{\n    ', b'}\n', b'\n}', b'\n]', b'\n  }',
    b'\n', b'\n  ', b'\n    ', b'\n      ', b'\n        ', b' ', b'  ', b'    ',
    b'\t', b'\t\t', b'\r\n', b': ', b' :', b' : ', b' , ', b' ,',
    b'"",', b'""', b'" ', b' "', b'"\n', b'",\n', b'",\n  ', b'"},\n',
]

_LITERALS = [b"true", b"false", b"null", b'"true"', b'"false"', b'"null"',
             b" true", b" false", b" null", b"true,", b"false,", b"null,",
             b"true}", b"false}", b"null}", b"true]", b"false]", b"null]"]

_NUMBERS = [
    b"10", b"11", b"12", b"13", b"14", b"15", b"16", b"17", b"18", b"19",
    b"20", b"21", b"22", b"23", b"24", b"25", b"30", b"31", b"32", b"40",
    b"42", b"50", b"60", b"64", b"70", b"80", b"90", b"99", b"100", b"101",
    b"123", b"127", b"128", b"200", b"255", b"256", b"365", b"400", b"404",
    b"500", b"512", b"999", b"1000", b"1024", b"2000", b"2020", b"2021",
    b"2022", b"2023", b"2024", b"2025", b"2026", b"4096", b"8080", b"65535",
    b"0.", b".0", b".5", b".25", b".75", b".99", b"0.0", b"0.5", b"1.0",
    b"1.5", b"2.5", b"3.14", b"9.99", b"19.99", b"99.99", b"-1", b"-0",
    b"-1.5", b"-10", b"-100", b"e10", b"e-5", b"E+", b"e+", b"1e", b"00",
    b"000", b"0000", b"01", b"02", b"03", b"09", b"1,", b"2,", b"0,", b"0}",
    b"1}", b"0]", b"1]", b", 0", b", 1", b", 2", b": 0", b": 1", b": 42",
]

_WORDS = """
the of and to in is it you that he was for on are with as his they be at one
have this from or had by hot word but what some we can out other were all
there when up use your how said an each she which do their time if will way
about many then them write would like so these her long make thing see him
two has look more day could go come did number sound no most people my over
know water than call first who may down side been now find any new work part
take get place made live where after back little only round man year came
show every good me give our under name very through just form sentence great
think say help low line differ turn cause much mean before move right boy old
too same tell does set three want air well also play small end put home read
hand port large spell add even land here must big high such follow act why
ask men change went light kind off need house picture try us again animal
point mother world near build self earth father head stand own page should
country found answer school grow study still learn plant cover food sun four
between state keep eye never last let thought city tree cross farm hard start
might story saw far sea draw left late run don't while press close night real
life few north open seem together next white children begin got walk example
ease paper group always music those both mark often letter until mile river
car feet care second book carry took science eat room friend began idea fish
mountain stop once base hear horse cut sure watch color face wood main enough
plain girl usual young ready above ever red list though feel talk bird soon
body dog family direct pose leave song measure door product black short
numeral class wind question happen complete ship area half rock order fire
south problem piece told knew pass since top whole king space heard best hour
better true during hundred five remember step early hold west ground interest
reach fast verb sing listen six table travel less morning ten simple several
vowel toward war lay against pattern slow center love person money serve
appear road map rain rule govern pull cold notice voice unit power town fine
certain fly fall lead cry dark machine note wait plan figure star box noun
field rest correct able pound done beauty drive stood contain front teach
week final gave green oh quick develop ocean warm free minute strong special
mind behind clear tail produce fact street inch multiply nothing course stay
wheel full force blue object decide surface deep moon island foot system busy
test record boat common gold possible plane stead dry wonder laugh thousand
ago ran check game shape equate miss brought heat snow tire bring yes distant
fill east paint language among alpha beta gamma delta lorem ipsum dolor sit
amet hello world foo bar baz qux test example sample data value item entry
user admin guest active inactive pending done error success failure warning
info debug none unknown default custom public private internal external
"""

_KEYS = """
id name email first_name last_name username password age status type kind
tags items children next value parent count total price quantity currency
amount description title body text content url href image thumbnail created
created_at updated_at deleted_at timestamp date time start end start_date
end_date address street city state zip zipcode postal_code country phone
mobile lat lng latitude longitude location geo coordinates enabled active
visible published draft archived version schema meta metadata data payload
result results error errors message code reason label labels category
categories group groups role roles permissions scope token session order
orders customer product products sku inventory stock rating reviews comment
comments author owner assignee reporter priority severity project issue
ticket event events source target parent_id child_id user_id order_id
product_id customer_id account balance limit offset page size per_page
sort filter query search index key values options settings config
preferences theme locale language timezone format encoding width height
depth color colors size weight unit units min max minimum maximum avg mean
median first last prev previous head tail left right node nodes edge edges
graph tree root leaf level path file files folder dir name_first name_last
""".split()

_SUBSTRINGS = [
    b"http://", b"https://", b"www.", b".com", b".org", b".io", b"example.com",
    b"@example.com", b"user@", b"@gmail.com", b"mailto:", b"-", b"_", b"--",
    b"__", b"..", b"...", b"://", b"/api/", b"/v1/", b"?q=", b"&", b"=", b"#",
    b"2024-01-01", b"2024-", b"-01-", b"-12-31", b"T00:00:00Z", b"T12:34:56Z",
    b"T", b"Z", b":00", b":30", b"00:", b"12:", b"+00:00", b"-05:00",
    b"123e4567", b"e89b", b"12d3", b"a456", b"426614174000", b"-e89b-",
    b"-12d3-", b"-a456-", b"abcdef", b"0123456789", b"deadbeef", b"cafe",
    b"ffff", b"0000", b"a1b2c3", b"xyz", b"abc", b"aaaa", b"aaaaaaaa",
    b"aaaaaaaaaaaaaaaa", b"bbbb", b"ab", b"abab", b"abababab", b"xxxx",
    b"xxxxxxxx", b"yyyy", b"zzzz", b"#ff0000", b"#00ff00", b"#0000ff",
    b"1.2.3", b"0.1.0", b"v1.0.0", b"+1-555-", b"555-1234", b"(555)",
    b"192.168.", b"10.0.0.1", b"127.0.0.1", b"255.255.255.0", b"::1",
    b"ABC-", b"XYZ-", b"ID-", b"ORD-", b"USR-", b"-000", b"-001",
    b"\\n", b'\\"', b"\\\\", b"\\t", b"\\r", b"\\u", b"\\u00", b"\\u00e9",
    b"\\u4e2d", b"\\ud83d", b"\\ude00", b"\\/",
    "é".encode(), "ü".encode(), "ñ".encode(), "ß".encode(), "ç".encode(),
    "→".encode(), "€".encode(), "£".encode(), "日本".encode(), "中文".encode(),
    "한국".encode(), "😀".encode(), "👍".encode(), "🚀".encode(), "ä".encode(),
    "ö".encode(), "α".encode(), "β".encode(), "Ω".encode(), "λ".encode(),
    "Ж".encode(), "я".encode(), "مرحبا".encode(), "שלום".encode(),
    "é".encode(), "\u200b".encode(), "\ufeff".encode(),
]


@functools.lru_cache(maxsize=None)
def build_vocabulary(extra_keys: typing.Tuple[str, ...] = ()) -> typing.Tuple[bytes, ...]:
    """Return the deterministic synthetic vocabulary as a tuple of byte strings.

    Index ``i`` is token id ``i``.  Ids 0-255 are the single bytes.  The result
    is de-duplicated so that no two ids share the same bytes.
    """
    seen: set[bytes] = set()
    out: list[bytes] = []

    def add(tok: bytes) -> None:
        if tok and tok not in seen:
            seen.add(tok)
            out.append(tok)

    for i in range(256):
        add(bytes([i]))
    for tok in _PUNCT + _LITERALS + _NUMBERS:
        add(tok)
    words = _WORDS.split()
    for w in words:
        add(w.encode())
    for w in words[:400]:
        add((" " + w).encode())
        add(w.capitalize().encode())
    for w in words[:200]:
        add(('"' + w).encode())
        add((w + '"').encode())
    for k in list(_KEYS) + list(extra_keys):
        add(k.encode())
        add(('"' + k + '"').encode())
        add(('"' + k + '":').encode())
        add(('"' + k + '": ').encode())
    for tok in _SUBSTRINGS:
        add(tok)
    return tuple(out)


def kbnf_vocabulary(tokens: typing.Sequence[bytes]):
    """Wrap the byte tokens in a ``kbnf.Vocabulary``."""
    import kbnf

    id_to_token = {i: kbnf.Token(t) for i, t in enumerate(tokens)}
    id_to_str = {i: t.decode("utf-8", "replace") for i, t in enumerate(tokens)}
    return kbnf.Vocabulary(id_to_token, id_to_str)


def decode_bytes(tokens: typing.Sequence[bytes], ids: typing.Iterable[int]) -> bytes:
    return b"".join(tokens[i] for i in ids)


# --------------------------------------------------------------------------
# Real tokenizer vocabularies
# --------------------------------------------------------------------------


def vocab_name_from_tokenizer(tokenizer_id: str) -> str:
    """``Qwen/Qwen2.5-0.5B-Instruct`` -> ``qwen2.5``; ``meta-llama/Llama-3.1-8B`` -> ``llama``.

    The last path component, lower-cased, up to the first ``-`` (which is where
    HF ids usually switch from the model family to size/variant).  Override
    with ``--vocab-name`` when the heuristic is wrong.
    """
    tail = tokenizer_id.rstrip("/").split("/")[-1].lower()
    head = tail.split("-", 1)[0]
    return "".join(ch for ch in head if ch.isalnum() or ch in "._") or "vocab"


def default_vocab_file(results_dir: str, name: str) -> str:
    return os.path.join(results_dir, f"vocab-{name}.pkl")


def build_vocab_file(tokenizer_id: str, path: str, name: str | None = None,
                     log: typing.Callable[[str], None] = lambda s: None) -> dict:
    """Load ``tokenizer_id`` with ``transformers``, build the engine vocabulary the
    way ``formatron.integrations.transformers.create_engine_vocabulary`` does, and
    pickle the raw maps to ``path``.  Returns the metadata dict (no token maps).

    The ``kbnf.Vocabulary`` returned by ``create_engine_vocabulary`` is built too,
    to assert that the pickled maps reproduce Formatron's own integration path
    (same size, same id->string mapping on a sample of ids).
    """
    import time

    t0 = time.perf_counter()
    from transformers import AutoTokenizer  # slow (~20 s): parent process only

    from formatron.integrations.transformers import create_engine_vocabulary
    from formatron.integrations.utils import get_original_characters

    log(f"[vocab] imported transformers in {time.perf_counter() - t0:.1f} s; loading {tokenizer_id!r}")
    t1 = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_id)
    raw = tokenizer.get_vocab()  # {str: id}, mangled the way the tokenizer files spell tokens
    id_to_bytes = get_original_characters(raw)  # {id: bytes}, unmangled (what create_engine_vocabulary feeds kbnf)
    id_to_str = {token_id: text for text, token_id in raw.items()}
    engine_vocab = create_engine_vocabulary(tokenizer)
    size = engine_vocab.get_vocab_size()
    if size != len(id_to_bytes) or size != len(id_to_str):
        raise RuntimeError(f"vocabulary size mismatch: kbnf {size}, bytes map {len(id_to_bytes)}, str map {len(id_to_str)}")
    step = max(1, size // 512)
    for token_id in list(range(0, size, step)) + [size - 1]:
        if token_id in id_to_str and engine_vocab.get_token_string(token_id) != id_to_str[token_id]:
            raise RuntimeError(f"id->string mismatch at token {token_id}")
    ids = sorted(id_to_bytes)
    holes = ids[-1] + 1 - len(ids) if ids else 0
    single_bytes = {b[0] for b in id_to_bytes.values() if len(b) == 1}
    meta = {
        "format": VOCAB_FILE_FORMAT,
        "name": name or vocab_name_from_tokenizer(tokenizer_id),
        "tokenizer": tokenizer_id,
        "size": size,
        "max_id": ids[-1] if ids else -1,
        "id_holes": holes,
        "missing_single_bytes": 256 - len(single_bytes),
        "eos_token_id": getattr(tokenizer, "eos_token_id", None),
        "tokenizer_class": type(tokenizer).__name__,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump({**meta, "id_to_bytes": id_to_bytes, "id_to_str": id_to_str}, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, path)
    log(f"[vocab] {meta['name']}: {size:,} tokens (max id {meta['max_id']}, {holes} id holes, "
        f"{meta['missing_single_bytes']} single bytes missing) built in {time.perf_counter() - t1:.1f} s -> {path}")
    return meta


def read_vocab_meta(path: str) -> dict | None:
    """Metadata of an existing vocab file (``None`` if missing/unreadable)."""
    try:
        data = load_vocab_file(path)
    except (OSError, pickle.UnpicklingError, EOFError, KeyError, ValueError):
        return None
    return {k: v for k, v in data.items() if k not in ("id_to_bytes", "id_to_str")}


@functools.lru_cache(maxsize=2)
def load_vocab_file(path: str) -> dict:
    """Unpickle a vocab file written by ``build_vocab_file`` (cached per path)."""
    with open(path, "rb") as f:
        data = pickle.load(f)
    if data.get("format") != VOCAB_FILE_FORMAT or "id_to_bytes" not in data or "id_to_str" not in data:
        raise ValueError(f"{path} is not a GrammarGuard vocab file (format {data.get('format')!r})")
    return data


def token_table(id_to_bytes: dict[int, bytes]) -> tuple[bytes, ...]:
    """Dense ``tokens[id] -> bytes`` table (holes in the id space become ``b""``)."""
    if not id_to_bytes:
        return ()
    table = [b""] * (max(id_to_bytes) + 1)
    for token_id, raw in id_to_bytes.items():
        table[token_id] = raw
    return tuple(table)


def kbnf_vocabulary_from_maps(id_to_bytes: dict[int, bytes], id_to_str: dict[int, str]):
    """Reconstruct the ``kbnf.Vocabulary`` a child needs from the pickled maps."""
    import kbnf

    return kbnf.Vocabulary({k: kbnf.Token(v) for k, v in id_to_bytes.items()}, dict(id_to_str))


def vocab_meta_from_options(options: dict) -> dict:
    """Small ``vocab`` descriptor stored in every result row."""
    path = options.get("vocab_file")
    if not path:
        return {"name": "synthetic", "tokenizer": None}
    meta = read_vocab_meta(path) or {}
    return {"name": options.get("vocab_name") or meta.get("name") or "unknown", "tokenizer": meta.get("tokenizer"),
            "size": meta.get("size")}


class GreedyTokenizer:
    """Minimal tokenizer object accepted by ``llguidance.TokenizerWrapper``.

    Only used so that llguidance can build an ``LLTokenizer`` over the
    synthetic vocabulary; the greedy longest-match encoding is never used for
    benchmark measurements.
    """

    def __init__(self, tokens: typing.Sequence[bytes]):
        self.tokens = list(tokens) + [EOS_TEXT]
        self.eos_token_id = len(self.tokens) - 1
        self.bos_token_id = None
        self.special_token_ids = [self.eos_token_id]
        self._index = {t: i for i, t in enumerate(self.tokens)}
        self._max_len = max(len(t) for t in self.tokens)

    def __call__(self, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        out = []
        i = 0
        while i < len(data):
            for length in range(min(self._max_len, len(data) - i), 0, -1):
                idx = self._index.get(data[i : i + length])
                if idx is not None:
                    out.append(idx)
                    i += length
                    break
            else:  # pragma: no cover - every single byte is in the vocab
                raise ValueError("unreachable: byte not in vocabulary")
        return out


if __name__ == "__main__":
    toks = build_vocabulary()
    print(f"{len(toks)} tokens; longest {max(map(len, toks))} bytes")
