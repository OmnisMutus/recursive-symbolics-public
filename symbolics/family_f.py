"""Family-F deterministic solver, output verification gate, and Candidate-1 Hebrew episode generator.

Implements Sections 2, 3, 6, and 7 of docs/ASSEMBLY_GUIDE.md (Dihedral Group D_22 Permutation Family) using standard-library Python only:
- 44 dihedral substitutions on Z_22: i -> (shift + sign * i) mod 22 (Atbash, Albam, Avgad, etc.).
- Positional & row readings: id, reverse, rotate_1..7, notariqon_initials/finals, interleave, boustrophedon.
- Exact rule enumeration over all 44 * 13 = 572 substitution x positional rules.
- Independent VERIFIED / CONTRADICTED / UNCHECKED gate for tzeruf_apply (approval never changes status).
- Candidate-1 Hebrew episode generator enforcing gold-cipher, reflect+reverse, attested-word, and 20% word exclusions.
"""
from dataclasses import dataclass
import hashlib
import random
import re
from typing import Any, Callable, Dict, Optional, Sequence

LETTERS = "אבגדהוזחטיכלמנסעפצקרשת"
_INDEX = {c: i for i, c in enumerate(LETTERS)}
FINALS = {"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"}
NIQQUD = re.compile(r"[\u0591-\u05C7]")

GOLD_CIPHERS = frozenset({"Atbash", "Albam", "Avgad"})
ATTESTED_WORDS = frozenset({"יהוה", "כוזו", "מצפץ"})

POSITIONAL_NAMES = (
    "id",
    "reverse",
    "rotate_1",
    "rotate_2",
    "rotate_3",
    "rotate_4",
    "rotate_5",
    "rotate_6",
    "rotate_7",
    "notariqon_initials",
    "notariqon_finals",
    "interleave",
    "boustrophedon",
)

# Fallback sample words (torah-like 2..8 letter forms) used only if caller supplies no word_pool.
DEFAULT_WORD_POOL = (
    "אמת", "שלום", "אהבה", "אחד", "רוח", "אור", "חיים", "ברכה", "דרך", "דעת",
    "חכמה", "בינה", "חסד", "גבורה", "תפארת", "נצח", "הוד", "יסוד", "מלכות", "כתר",
    "בראשית", "שמים", "ארץ", "משה", "ישראל", "תורה", "לב", "מים", "אש", "עץ",
    "תולדות", "המאורות", "וכוכבים", "משפחותם", "כדמותנו", "והאלהים", "וישמרו", "וממלכות",
)


def normalize_hebrew(text: str) -> str:
    """Strip niqqud, map final letters to base forms, and normalize inter-word whitespace."""
    if not isinstance(text, str):
        return ""
    stripped = NIQQUD.sub("", text)
    mapped = "".join(c if c in _INDEX else FINALS[c] if c in FINALS else " " for c in stripped)
    return " ".join(mapped.split())


_ATTESTED_NORM = frozenset(normalize_hebrew(w) for w in ATTESTED_WORDS)


def _dihedral_name(sign: int, shift: int) -> str:
    if sign == 1:
        if shift == 0:
            return "id"
        if shift == 1:
            return "Avgad"
        if shift == 11:
            return "Albam"
        if shift == 21:
            return "Reverse_Avgad"
        return f"shift_{shift}"
    if shift == 21:
        return "Atbash"
    return f"reflect_{shift}"


@dataclass(frozen=True)
class DihedralSub:
    name: str
    sign: int
    shift: int

    def apply(self, text: str) -> Optional[str]:
        return apply_dihedral(text, self.sign, self.shift)


DIHEDRAL_RULES: tuple[DihedralSub, ...] = tuple(
    DihedralSub(_dihedral_name(sign, shift), sign, shift)
    for sign in (1, -1)
    for shift in range(22)
)


def apply_dihedral(text: str, sign: int, shift: int) -> Optional[str]:
    """Apply i -> (shift + sign * i) mod 22 across normalized Hebrew letters, preserving single spaces."""
    if sign not in (1, -1):
        raise ValueError(f"sign must be +1 or -1, got {sign!r}")
    norm = normalize_hebrew(text)
    if not norm:
        return None
    n_letters = len(LETTERS)
    return "".join(
        " " if c == " " else LETTERS[(shift + sign * _INDEX[c]) % n_letters]
        for c in norm
    )


def apply_positional(text: str, pos: str) -> Optional[str]:
    """Apply a Family-F positional or row reading to normalized Hebrew text."""
    norm = normalize_hebrew(text)
    if not norm:
        return None
    words = norm.split(" ")
    if pos == "id":
        return norm
    if pos == "reverse":
        return " ".join(w[::-1] for w in words[::-1])
    if pos.startswith("rotate_"):
        k = int(pos.split("_", 1)[1])
        if not 1 <= k <= 7:
            raise ValueError(f"unsupported rotation {pos!r}")
        if len(words) != 1 or len(words[0]) <= k:
            return None
        w = words[0]
        return w[k:] + w[:k]
    if pos == "notariqon_initials":
        if not (2 <= len(words) <= 4 and all(words)):
            return None
        return "".join(w[0] for w in words)
    if pos == "notariqon_finals":
        if not (2 <= len(words) <= 4 and all(words)):
            return None
        return "".join(w[-1] for w in words)
    if pos == "interleave":
        if len(words) != 2 or not words[0] or len(words[0]) != len(words[1]):
            return None
        return "".join(a + b for a, b in zip(words[0], words[1]))
    if pos == "boustrophedon":
        if len(words) != 3 or not words[0] or not (len(words[0]) == len(words[1]) == len(words[2])):
            return None
        r1, r2, r3 = words
        length = len(r1)
        if length == 1:
            return r1[0] + r2[0] + r3[0]
        return " ".join(r1[i] + r2[length - 1 - i] + r3[i] for i in range(length))
    raise ValueError(f"unknown positional rule {pos!r}")


@dataclass(frozen=True)
class Rule:
    """A Family-F rule composing one dihedral substitution and one positional reading."""

    sub_name: str
    sign: int
    shift: int
    pos: str

    @property
    def complexity(self) -> int:
        return int(self.sub_name != "id") + int(self.pos != "id")

    @property
    def name(self) -> str:
        if self.sub_name == "id" and self.pos == "id":
            return "id"
        if self.pos == "id":
            return self.sub_name
        if self.sub_name == "id":
            return self.pos
        return f"{self.sub_name}+{self.pos}"

    def apply(self, text: str) -> Optional[str]:
        subbed = apply_dihedral(text, self.sign, self.shift)
        if subbed is None:
            return None
        return apply_positional(subbed, self.pos)


ALL_RULES: tuple[Rule, ...] = tuple(
    sorted(
        (
            Rule(sub.name, sub.sign, sub.shift, pos)
            for sub in DIHEDRAL_RULES
            for pos in POSITIONAL_NAMES
        ),
        key=lambda r: (r.complexity, POSITIONAL_NAMES.index(r.pos), 0 if r.sign == 1 else 1, r.shift),
    )
)
RULE_BY_NAME: dict[str, Rule] = {r.name: r for r in ALL_RULES}


def matching_rules(study: Sequence[tuple[str, str]]) -> list[Rule]:
    """Return every Family-F rule consistent with all (input, output) study pairs."""
    if not study:
        return []
    norm_study: list[tuple[str, str]] = []
    for x, y in study:
        nx = normalize_hebrew(x)
        ny = normalize_hebrew(y)
        if not nx or not ny:
            return []
        norm_study.append((nx, ny))
    return [r for r in ALL_RULES if all(r.apply(x) == y for x, y in norm_study)]


def _distinct_outputs(rules: Sequence[Rule], query_norm: str) -> list[str]:
    outs: list[str] = []
    seen: set[str] = set()
    for rule in rules:
        val = rule.apply(query_norm)
        if val is not None and val not in seen:
            seen.add(val)
            outs.append(val)
    return outs


def _simplest_rules(matches: Sequence[Rule], query_norm: str) -> list[Rule]:
    """Of the rules that fit the study, those that apply to this query and are the simplest (fewest non-id parts)."""
    defined = [r for r in matches if r.apply(query_norm) is not None] if query_norm else []
    if not defined:
        return []
    min_c = min(r.complexity for r in defined)
    return [r for r in defined if r.complexity == min_c]


def check_outputs(
    study: Sequence[tuple[str, str]],
    query_outputs: Sequence[tuple[str, str]],
    approved: bool = False,
) -> dict:
    """Verify proposed outputs against Family F; human approval never alters status.

    Each proposal is judged by the simplest rules that fit the study and apply to its query. If they all give one
    output, the proposal is VERIFIED when it equals it and CONTRADICTED when it does not. If they disagree, a
    proposal none of them gives is CONTRADICTED, and one that some give is UNCHECKED, since the study cannot tell
    which rule was meant. With no such rule at all, it is UNCHECKED."""
    matches = matching_rules(study)
    return {
        "approved": bool(approved),
        "matched_rules": [r.name for r in matches],
        "results": [_check_one(matches, query, proposed) for query, proposed in query_outputs],
    }


def _check_one(matches: Sequence[Rule], query: str, proposed: str) -> dict:
    q_norm = normalize_hebrew(query)
    tier = _simplest_rules(matches, q_norm)
    result = {"query": query, "proposed": proposed}
    if not tier:
        return dict(result, status="UNCHECKED", checker_output=None, rule=None)
    outs = _distinct_outputs(tier, q_norm)
    p_norm = normalize_hebrew(proposed)
    if len(outs) == 1:
        status = "VERIFIED" if p_norm == outs[0] else "CONTRADICTED"
        return dict(result, status=status, checker_output=outs[0], rule=tier[0].name)
    if p_norm not in outs:
        return dict(result, status="CONTRADICTED", checker_output=outs[0], candidates=outs, rule=tier[0].name)
    return dict(result, status="UNCHECKED", reason="ambiguous_study", checker_output=None, candidates=outs, rule=None)


def tzeruf_apply(
    study: Sequence[tuple[str, str]],
    queries: Sequence[str],
    model_predict: Optional[Callable[[Sequence[tuple[str, str]], Sequence[str]], Sequence[str]]] = None,
    approved: bool = False,
) -> dict:
    """Propose outputs for queries given study pairs and verify them through the Family-F gate."""
    matches = matching_rules(study)
    if model_predict is None:
        # The checker's own proposal: what the first of the simplest fitting rules gives, or "" if none applies.
        proposals: list[str] = []
        for q in queries:
            q_norm = normalize_hebrew(q)
            tier = _simplest_rules(matches, q_norm)
            proposals.append((tier[0].apply(q_norm) or "") if tier else "")
    else:
        raw = list(model_predict(study, queries))
        if len(raw) != len(queries):
            raise ValueError(f"model_predict returned {len(raw)} outputs for {len(queries)} queries")
        proposals = [str(p) for p in raw]
    return check_outputs(study, list(zip(queries, proposals)), approved=approved)


def is_held_out_word(word: str) -> bool:
    """Return True for attested reserve words or the deterministic 20% held-out Torah partition."""
    norm = normalize_hebrew(word)
    if not norm:
        return False
    if norm in _ATTESTED_NORM:
        return True
    digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 5 == 0


class HebrewGrammar:
    """Episodic meta-grammar assigning 2 or 3 meaningless operator tokens to Family-F rules."""

    def __init__(self, ops: dict[str, Rule]):
        if not ops:
            raise ValueError("ops must contain at least one operator mapping")
        self.ops: dict[str, Rule] = dict(ops)

    def signature(self) -> tuple[tuple[int, int, str], ...]:
        """Semantic canonical signature invariant to operator token names and ordering."""
        return tuple(sorted((r.sign, r.shift, r.pos) for r in self.ops.values()))

    def has_gold_or_held_out_composition(self) -> bool:
        """Return True if any operator uses a gold cipher (Atbash/Albam/Avgad) or reflect+reverse."""
        for rule in self.ops.values():
            if rule.sub_name in GOLD_CIPHERS:
                return True
            if rule.sign == -1 and rule.pos == "reverse":
                return True
        return False

    def interpret(self, tokens: Sequence[str]) -> Optional[str]:
        """Apply postfix operators left-to-right over Hebrew word/phrase segments."""
        if not tokens:
            return None
        segments: list[str] = []
        buf: list[str] = []
        i = 0
        n = len(tokens)
        while i < n:
            tok = tokens[i]
            if tok in self.ops:
                if not buf:
                    return None
                cur: Optional[str] = normalize_hebrew(" ".join(buf))
                buf = []
                if not cur:
                    return None
                while i < n and tokens[i] in self.ops:
                    cur = self.ops[tokens[i]].apply(cur)
                    if cur is None:
                        return None
                    i += 1
                segments.append(cur)
            else:
                norm_tok = normalize_hebrew(tok)
                if not norm_tok:
                    return None
                buf.append(norm_tok)
                i += 1
        if buf:
            tail = normalize_hebrew(" ".join(buf))
            if not tail:
                return None
            segments.append(tail)
        return " ".join(segments) if segments else None


_NON_TRIVIAL_RULES: tuple[Rule, ...] = tuple(r for r in ALL_RULES if r.complexity >= 1)


def sample_hebrew_grammar(rng: random.Random, n_ops: Optional[int] = None) -> HebrewGrammar:
    """Sample a 2- or 3-operator Candidate-1 grammar mapping tokens to Family-F rules."""
    k = n_ops if n_ops is not None else rng.choice((2, 3))
    rules = rng.sample(_NON_TRIVIAL_RULES, k)
    return HebrewGrammar({f"op{idx + 1}": rule for idx, rule in enumerate(rules)})


def _candidate_tokens(rng: random.Random, gr: HebrewGrammar, words: Sequence[str]) -> tuple[str, ...]:
    op_names = list(gr.ops.keys())
    op_a = rng.choice(op_names)
    pos = gr.ops[op_a].pos
    if pos in ("notariqon_initials", "notariqon_finals"):
        n_w = rng.randint(2, min(4, len(words))) if len(words) >= 2 else 1
        return tuple(rng.choices(words, k=n_w)) + (op_a,)
    if pos == "interleave":
        by_len: dict[int, list[str]] = {}
        for w in words:
            by_len.setdefault(len(w), []).append(w)
        valid_lens = [k for k, v in by_len.items() if v]
        chosen_len = rng.choice(valid_lens)
        w1, w2 = rng.choices(by_len[chosen_len], k=2)
        return (w1, w2, op_a)
    if pos == "boustrophedon":
        by_len = {}
        for w in words:
            by_len.setdefault(len(w), []).append(w)
        valid_lens = [k for k, v in by_len.items() if v]
        chosen_len = rng.choice(valid_lens)
        w1, w2, w3 = rng.choices(by_len[chosen_len], k=3)
        return (w1, w2, w3, op_a)
    pool = words
    if pos.startswith("rotate_"):
        rot_k = int(pos.split("_", 1)[1])
        longer = [w for w in words if len(w) > rot_k]
        if longer:
            pool = longer
    w = rng.choice(pool)
    single_word_ops = [
        name for name, rule in gr.ops.items()
        if rule.pos in ("id", "reverse") or (rule.pos.startswith("rotate_") and len(w) > int(rule.pos.split("_", 1)[1]))
    ]
    if single_word_ops and rng.random() < 0.35:
        op_b = rng.choice(single_word_ops)
        return (w, op_a, op_b)
    return (w, op_a)


def _grammar_feasible_for_pool(gr: HebrewGrammar, words: Sequence[str]) -> bool:
    max_len = max(len(w) for w in words)
    for rule in gr.ops.values():
        if rule.pos.startswith("rotate_"):
            rot_k = int(rule.pos.split("_", 1)[1])
            if max_len <= rot_k:
                return False
    return True


def sample_hebrew_episode(
    rng: random.Random,
    word_pool: Optional[Sequence[str]] = None,
    n_study: int = 10,
    n_query: int = 6,
    max_tries: int = 4000,
) -> tuple[HebrewGrammar, list[tuple[tuple[str, ...], str]], list[tuple[tuple[str, ...], str]]]:
    """Sample a Candidate-1 training episode respecting gold/held-out/length exclusions."""
    raw_pool = DEFAULT_WORD_POOL if word_pool is None else word_pool
    eligible: list[str] = []
    seen_words: set[str] = set()
    for w in raw_pool:
        nw = normalize_hebrew(w)
        if not nw or " " in nw or not (2 <= len(nw) <= 8) or is_held_out_word(nw):
            continue
        if nw not in seen_words:
            seen_words.add(nw)
            eligible.append(nw)
    if not eligible:
        raise ValueError("word_pool contains no eligible non-held-out single words of length 2..8")

    while True:
        gr = sample_hebrew_grammar(rng)
        if not gr.has_gold_or_held_out_composition() and _grammar_feasible_for_pool(gr, eligible):
            break

    study: list[tuple[tuple[str, ...], str]] = []
    query: list[tuple[tuple[str, ...], str]] = []
    seen_inputs: set[tuple[str, ...]] = set()
    needed = n_study + n_query
    for _ in range(max_tries):
        if len(study) + len(query) >= needed:
            break
        toks = _candidate_tokens(rng, gr, eligible)
        if toks in seen_inputs:
            continue
        out = gr.interpret(toks)
        if out is None:
            continue
        seen_inputs.add(toks)
        if len(study) < n_study:
            study.append((toks, out))
        else:
            query.append((toks, out))
    if len(study) < n_study or len(query) < n_query:
        raise RuntimeError("failed to sample enough distinct valid examples for Hebrew episode")
    return gr, study, query


def _normalize_study_pairs(raw_study: Sequence[Any]) -> Optional[list[tuple[str, str]]]:
    pairs: list[tuple[str, str]] = []
    for item in raw_study:
        if isinstance(item, dict):
            x, y = item.get("input", ""), item.get("output", "")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            x, y = item[0], item[1]
        else:
            return None
        sx, sy = str(x).strip(), str(y).strip()
        if not sx or not sy:
            return None
        pairs.append((sx, sy))
    return pairs


def _parse_tzeruf_text(text: str, a: Optional[str], b: Optional[str]) -> tuple[list[tuple[str, str]], list[str]]:
    parsed_study: list[tuple[str, str]] = []
    parsed_queries: list[str] = []
    if a is not None and b is not None and str(a).strip() and str(b).strip():
        parsed_study.append((str(a).strip(), str(b).strip()))
    if text:
        compact = re.sub(r"\s*(?:->|=)\s*", "=", str(text))
        for tok in re.split(r"[\s,;|]+", compact.strip()):
            if not tok:
                continue
            if "=" in tok:
                left, right = tok.split("=", 1)
                if left.strip() and right.strip():
                    parsed_study.append((left.strip(), right.strip()))
            else:
                parsed_queries.append(tok)
    return parsed_study, parsed_queries


def solve_tzeruf(
    text: str = "",
    a: Optional[str] = None,
    b: Optional[str] = None,
    study: Optional[Sequence[Any]] = None,
    queries: Optional[Sequence[str]] = None,
    proposed: Optional[Sequence[Optional[str]]] = None,
    approved: bool = False,
) -> Dict[str, Any]:
    """Invert Family-F cipher study pairs and apply/verify against queries (CLI & tool friendly)."""
    parsed_study: list[tuple[str, str]] = []
    parsed_queries: list[str] = []
    if study is not None:
        normalized = _normalize_study_pairs(study)
        if normalized is None:
            return {"error": "Each study entry must be [input, output] or {'input': ..., 'output': ...} with non-empty text."}
        parsed_study = normalized
        # Anything also given as text, or as a and b, is added. _parse_tzeruf_text returns nothing when there is
        # nothing to add, so no condition is needed here (one was, until 2026-11-22, and it changed nothing).
        extra_study, text_queries = _parse_tzeruf_text(text, a, b)
        parsed_study.extend(extra_study)
        parsed_queries.extend(text_queries)
    else:
        parsed_study, parsed_queries = _parse_tzeruf_text(text, a, b)

    if not parsed_study:
        return {
            "error": "Give at least one study pair (e.g. a='יהוה', b='כוזו', text='יהוה=כוזו אדני', or study=[['יהוה','כוזו']])."
        }

    query_list = [str(q) for q in queries] if queries is not None else parsed_queries
    if proposed is not None:
        if len(proposed) != len(query_list):
            return {"error": f"proposed length ({len(proposed)}) must match queries length ({len(query_list)})."}
        out = check_outputs(
            parsed_study,
            [(q, "" if p is None else str(p)) for q, p in zip(query_list, proposed)],
            approved=approved,
        )
    else:
        out = tzeruf_apply(parsed_study, query_list, approved=approved)

    results = out["results"]
    if results:
        statuses = [r["status"] for r in results]
        if "CONTRADICTED" in statuses:
            top_status = "CONTRADICTED"
        elif all(s == "VERIFIED" for s in statuses):
            top_status = "VERIFIED"
        else:
            top_status = "UNCHECKED"
    elif len(out["matched_rules"]) == 1:
        top_status = "VERIFIED"
    else:
        top_status = "UNCHECKED"

    out["status"] = top_status
    out["rule_count"] = len(out["matched_rules"])
    out["study"] = [{"input": x, "output": y} for x, y in parsed_study]
    return out

