"""KM encoding and printed-answer handling at the integration boundary."""

import re

_SAFE = re.compile(r"[A-Za-z][A-Za-z0-9_+-]*")
_RESERVED = frozenset("a some must-be-a mustnt-be-a print format km-format an instance @ retain-expr possible-values excluded-values spy unspy anonymous-instancep sanity-check every the the1 the2 the3 theN theNth of forall forall2 with where theoneof theoneof2 forall-seq forall-seq2 forall-bag forall-bag2 the-class constraints-for rules-for the+ a+ evaluate-paths clone a-prototype oneof oneof2 It It2 if then else allof allof2 in and or not is & && &? &+ &+? &+! &! &&! = === /= + - / ^ >= <= isa append are includes thelast showme-here showme showme-all evaluate-all quote delete evaluate has-value andify make-sentence make-phrase has now-has also-has also-hasnt now-has-definition must is-superset-of covers subsumes has-definition numberp bag seq no-inheritance comm get-justification trace untrace fluent-instancep at-least at-most exactly constraint <> reverse is-subsumed-by is-covered-by set-constraint set-filter in-situation in-every-situation end-situation do do-and-next in-theory end-theory see-theory hide-theory visible-theories curr-situation ignore-result do-script new-context do-plan set args triple pair function default".split())
_ABSENT = {"", "nil", "()"}
_RESERVED_LOWER = {word.lower() for word in _RESERVED} | {"nil", "t", "f", "true", "false"}



def player_frame(name: str) -> str:
    name = str(name or "").removeprefix("*")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name) or name.lower() == "global":
        raise ValueError("Invalid KM player situation name")
    return "*" + name


def frame(player: str, kind: str, identifier: str) -> str:
    player = player_frame(player)[1:]
    if not isinstance(identifier, str) or not identifier:
        raise ValueError("A KM frame requires a nonempty identity")
    return "*SOM-" + "-".join(value.encode("utf-8").hex() for value in (player, kind, identifier))


def token(name: str) -> str:
    return name if symbol(name) else km_string(name)


def symbol(name: str) -> bool:
    return _SAFE.fullmatch(name) is not None and name.lower() not in _RESERVED_LOWER


def one_line(text: str) -> str:
    return text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()


def km_string(text: str) -> str:
    return '"' + one_line(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def seq(values) -> str:
    return "(:seq" + "".join(" " + value for value in values) + ")"


def now_has(subject: str, pairs) -> str:
    return "(" + subject + " now-has " + " ".join(f"({slot} ({value}))" for slot, value in pairs) + ")"


def unwrap(answer: str) -> str:
    text = answer.strip()
    if len(text) >= 2 and text.startswith("(") and text.endswith(")"):
        return text[1:-1].strip()
    return text
