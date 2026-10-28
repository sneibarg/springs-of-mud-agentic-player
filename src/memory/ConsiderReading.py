import re

from dataclasses import dataclass


# Text from springs-of-mud-server Info.do_consider, in the order the server tests level difference.
_VERDICTS = (
    (re.compile(r"^You can kill (?P<name>.+) naked and weaponless\.$"), "naked", "safe"),
    (re.compile(r"^(?P<name>.+) is no match for you\.$"), "no_match", "safe"),
    (re.compile(r"^(?P<name>.+) looks like an easy kill\.$"), "easy_kill", "safe"),
    (re.compile(r"^The perfect match!$"), "even", "even"),
    (re.compile(r"^(?P<name>.+) says 'Do you feel lucky, punk\?'\.$"), "lucky", "risky"),
    (re.compile(r"^(?P<name>.+) laughs at you mercilessly\.$"), "laughs", "risky"),
    (re.compile(r"^Death will thank you for your gift\.$"), "death", "fatal"),
)

# Guards and position checks on the consider command. These are not fight estimates.
_REFUSALS = {
    "consider killing whom?",
    "they're not here.",
    "don't even think about it.",
    "lie still; you are dead.",
    "you are hurt far too bad for that.",
    "you are too stunned to do that.",
    "in your dreams, or what?",
}


@dataclass(frozen=True)
class ConsiderReading:
    target: str
    subject: str
    kind: str
    outlook: str
    verdict: str
    text: str

    @property
    def estimated(self) -> bool:
        return self.outlook in {"safe", "even", "risky", "fatal"}


def parse_consider(target: str, lines: list[str], *, kind: str) -> ConsiderReading:
    """Read one `consider` reply. `target` is the name the agent typed."""
    body = [line.strip() for line in lines if line and line.strip()]
    text = "\n".join(body)
    subject = target.strip()
    outlook = "unknown"
    verdict = "unrecognized"
    for line in body:
        refusal = line.lower()
        if refusal in _REFUSALS:
            subject = target.strip()
            outlook = "unknown"
            verdict = "refused"
            continue
        for pattern, verdict_name, outlook_name in _VERDICTS:
            match = pattern.match(line)
            if match is None:
                continue
            named = match.groupdict().get("name")
            if named:
                subject = named.strip()
            outlook = outlook_name
            verdict = verdict_name
    return ConsiderReading(
        target=target.strip(),
        subject=subject,
        kind=kind,
        outlook=outlook,
        verdict=verdict,
        text=text,
    )
