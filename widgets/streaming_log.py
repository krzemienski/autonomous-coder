"""Rich-formatted streaming log widget for agent output."""
from textual.widgets import RichLog

from ..messages import AgentOutput


class StreamingLog(RichLog):
    """RichLog that handles AgentOutput messages and renders with markup."""

    def on_agent_output(self, message: AgentOutput) -> None:
        """Render incoming agent output with appropriate markup."""
        block_type = message.block_type
        text = message.text

        if block_type == "tool":
            self.write(f"[bold cyan]\\[tool] {text}[/bold cyan]")
        elif block_type == "error":
            self.write(f"[bold red]{text}[/bold red]")
        elif block_type == "thinking":
            self.write(f"[dim italic]{text}[/dim italic]")
        elif block_type == "result":
            self.write(f"[green]{text}[/green]")
        else:
            # Plain text — pass through with markup support
            self.write(text)
