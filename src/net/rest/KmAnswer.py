from dataclasses import dataclass


@dataclass(frozen=True)
class KmAnswer:
    """One KM evaluation returned by som-nlp-service.

    `answer` is KM's printed syntax. An empty answer is the string `nil`.
    The service does not return the session.
    """

    ok: bool
    answer: str
    input: str = ""
    errors: tuple[str, ...] = ()
    message: str = ""

    @classmethod
    def from_json(cls, payload: object) -> "KmAnswer":
        if not isinstance(payload, dict):
            raise ValueError("KM result must be an object")
        answer = payload.get("answer")
        if answer is None:
            answer = ""
        if not isinstance(answer, str):
            raise ValueError("KM answer must be a string")
        errors = payload.get("errors") or ()
        if not isinstance(errors, (list, tuple)) or any(not isinstance(item, str) for item in errors):
            raise ValueError("KM errors must be a list of strings")
        message = payload.get("message") or ""
        if not isinstance(message, str):
            raise ValueError("KM message must be a string")
        text = payload.get("input") or ""
        if not isinstance(text, str):
            text = ""
        return cls(ok=bool(payload.get("ok")), answer=answer, input=text, errors=tuple(errors), message=message)
