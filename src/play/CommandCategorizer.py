from memory.WorkingMemory import WorkingMemory
from net.rest.OllamaClient import OllamaClient
from prompt.Prompt import Prompt, PromptSubmission


class CommandCategorizer:
    """Later phase: categorize one command from its help page.

    First login only remembers command names. This type fills `{command}` and
    `{help}` on a prompt and sends that body through `OllamaClient`. Bootstrap
    does not call it.
    """

    def __init__(self, client: OllamaClient | None = None, prompt: Prompt | None = None):
        self.client = client
        self.prompt = prompt

    def submission(self, command: str, help_text: str) -> PromptSubmission:
        """Build the completion body. This does not send it."""
        if self.prompt is None:
            raise RuntimeError("No command-category prompt is configured.")
        name = command.strip()
        if not name:
            raise ValueError("A command category needs a command name")
        user = _fill(self.prompt.user, name, help_text)
        system = _fill(self.prompt.system, name, help_text)
        if self.prompt.user.count("{command}") != 1 or self.prompt.user.count("{help}") != 1:
            raise ValueError(f"Prompt '{self.prompt.name}' is missing the {{command}} or {{help}} placeholder.")
        if not user.strip():
            raise ValueError("User prompt cannot be null or empty")
        return PromptSubmission(
            name=self.prompt.name,
            model=self.prompt.model,
            system=system,
            user=user,
            json_schema=dict(self.prompt.json_schema),
            intents=(),
        )

    def categorize(self, memory: WorkingMemory, command: str, help_text: str) -> str:
        """Send the prompt and store the category on the remembered command."""
        if self.client is None:
            raise RuntimeError("No Ollama client is configured.")
        submission = self.submission(command, help_text)
        parsed = submission.read_completion(self.client.complete(submission.to_request()))
        category = _category_name(parsed)
        memory.remember_command(command, category=category)
        return category


def _fill(template: str, command: str, help_text: str) -> str:
    return template.replace("{command}", command).replace("{help}", help_text)


def _category_name(parsed) -> str:
    if isinstance(parsed, dict):
        category = parsed.get("category", "")
    else:
        category = parsed
    if not isinstance(category, str) or not category.strip():
        raise ValueError("Ollama completion did not name a category")
    return category.strip()
