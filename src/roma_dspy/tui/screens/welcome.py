"""Welcome screen for TUI.

Displays animated logo with pulsing and typing effects while data loads.
"""

from __future__ import annotations

import math
from pathlib import Path

from loguru import logger
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Static


def _load_ascii_art(asset_name: str) -> str:
    """Load ASCII art from assets directory.

    Args:
        asset_name: Name of asset file

    Returns:
        ASCII art content or empty string if not found
    """
    try:
        asset_path = Path(__file__).parent.parent.parent.parent.parent / "assets" / asset_name
        if asset_path.exists():
            content = asset_path.read_text(encoding="utf-8").strip()
            logger.debug(f"Loaded asset '{asset_name}' ({len(content)} chars)")
            return content
        logger.warning(f"Asset '{asset_name}' not found at {asset_path}")
    except Exception as exc:
        logger.error(f"Failed loading asset '{asset_name}': {exc}")
        return ""
    return ""


# Load logos at module level
SENTIENT_LOGO = _load_ascii_art("sentient_logo_text_ascii.txt")
ROMA_LOGO = _load_ascii_art("roma_logo_simple_visible.txt")


class WelcomeScreen(ModalScreen[None]):
    """Animated welcome screen with logo and loading indicator."""

    CSS = """
    WelcomeScreen {
        align: center middle;
        background: $surface;
    }

    #welcome-container {
        min-width: 60;
        min-height: 20;
        width: auto;
        height: auto;
        background: $surface;
        border: solid $primary;
        padding: 2 4;
    }

    #welcome-logo {
        text-align: center;
        margin-bottom: 2;
        width: 100%;
    }

    #welcome-message {
        text-align: center;
        margin-top: 1;
        width: 100%;
    }

    #loading-spinner {
        text-align: center;
        margin-top: 1;
        width: 100%;
    }
    """

    # Animation constants
    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, execution_id: str, browser_context: dict | None = None) -> None:
        """Initialize welcome screen.

        Args:
            execution_id: Execution ID being loaded
            browser_context: Browser context for back navigation (optional)
        """
        super().__init__()
        self.execution_id = execution_id
        self.browser_context = browser_context
        self.data_loaded = False
        self.spinner_index = 0
        self.pulse_phase = 0
        self.typing_progress = 0
        self.pulse_intensity = 0.0
        self.animation_timer = None

    def compose(self) -> ComposeResult:
        """Compose welcome screen layout.

        Yields:
            Welcome screen components
        """
        # Combine logos
        sentient_logo = SENTIENT_LOGO if SENTIENT_LOGO else "SENTIENT"
        roma_logo = ROMA_LOGO if ROMA_LOGO else "ROMA-DSPy"
        combined_logo = f"{sentient_logo}\n\n{roma_logo}"

        with Container(id="welcome-container"):
            yield Static(combined_logo, id="welcome-logo")
            yield Static(
                f"Loading execution {self.execution_id[:8]}...",
                id="welcome-message"
            )
            yield Static("", id="loading-spinner")

    def on_mount(self) -> None:
        """Start animations when mounted."""
        # Start animation loop at 15 FPS for smooth animations
        self.animation_timer = self.set_interval(0.067, self._update_animations)
        logger.debug("Welcome screen mounted, animations started")

    def _update_animations(self) -> None:
        """Update all animations: spinner, pulsing, and typing effects."""
        # Update spinner
        spinner_widget = self.query_one("#loading-spinner", Static)
        self.spinner_index = (self.spinner_index + 1) % len(self.SPINNER_FRAMES)
        spinner = self.SPINNER_FRAMES[self.spinner_index]

        if not self.data_loaded:
            # Add pulsing dots
            dots_count = (self.spinner_index // 3) % 4
            dots = "." * dots_count
            spinner_widget.update(f"[steel_blue1]{spinner}[/] Loading{dots}")
        else:
            # Clear spinner after loading
            spinner_widget.update("")

        # Animate logo (always, even after data loads)
        logo_widget = self.query_one("#welcome-logo", Static)

        # Update pulse intensity (sine wave for smooth pulsing)
        self.pulse_intensity = (math.sin(self.pulse_phase * 0.05) + 1.0) / 2.0  # 0.0 to 1.0

        # Increase typing progress (2 characters per frame)
        sentient_logo = SENTIENT_LOGO if SENTIENT_LOGO else "SENTIENT"
        roma_logo = ROMA_LOGO if ROMA_LOGO else "ROMA-DSPy"
        combined_logo = f"{sentient_logo}\n\n{roma_logo}"

        if self.typing_progress < len(combined_logo):
            self.typing_progress = min(self.typing_progress + 2, len(combined_logo))

        # Apply pulsing and typing effects
        animated_logo = self._apply_logo_effects(combined_logo)
        logo_widget.update(animated_logo)

        self.pulse_phase += 1

    def _apply_logo_effects(self, text: str) -> Text:
        """Apply pulsing and typing effects to logo.

        Args:
            text: Logo text

        Returns:
            Rich Text with effects applied
        """
        result = Text()
        char_count = 0

        # Separate ASCII art from text labels
        lines = text.split('\n')
        text_line_indices = []

        # Identify text lines (contain "SENTIENT" or "ROMA"/"DSPy")
        for idx, line in enumerate(lines):
            if 'SENTIENT' in line or 'ROMA' in line or 'DSPy' in line:
                text_line_indices.append(idx)

        for line_idx, line in enumerate(lines):
            is_text_line = line_idx in text_line_indices

            for char in line:
                # Always show newlines
                if char == '\n':
                    result.append(char)
                    continue

                # Apply typing effect: only show characters up to typing_progress
                if char_count >= self.typing_progress:
                    break

                if char.strip():  # Non-whitespace character
                    if is_text_line:
                        # Text parts: typing effect with steel_blue1
                        result.append(char, style="steel_blue1")
                    else:
                        # ASCII art: strong pulsing effect with blue shades only
                        if self.pulse_intensity < 0.33:
                            color = "blue"  # Darker blue
                        elif self.pulse_intensity < 0.67:
                            color = "dodger_blue1"  # Medium blue
                        else:
                            color = "cyan"  # Bright cyan

                        # Add bold for expansion effect when pulse is high
                        if self.pulse_intensity > 0.5:
                            result.append(char, style=f"bold {color}")
                        else:
                            result.append(char, style=color)

                    char_count += 1
                else:
                    # Whitespace
                    result.append(char)
                    char_count += 1

            # Add newline after each line (if within typing progress)
            if line_idx < len(lines) - 1 and char_count < self.typing_progress:
                result.append('\n')

        return result

    def on_key(self, event: events.Key) -> None:
        """Handle key press events.

        Follows SRP: Only routes key events to handler methods.

        Args:
            event: Key event
        """
        if event.key == "enter":
            self._handle_enter_key()
        elif event.key == "b":
            self._handle_back_key()
        elif event.key == "q":
            self._handle_quit_key()

    def _handle_enter_key(self) -> None:
        """Handle Enter key press to continue to main screen.

        Follows SRP: Only handles Enter key logic.
        """
        if self.data_loaded:
            # Data is loaded, allow dismissal
            logger.debug("User dismissed welcome screen - calling dismiss(True)")
            self.dismiss(True)  # Return True to indicate successful load
            logger.debug("dismiss() called")
        else:
            # Data still loading, show warning
            self._show_loading_warning()

    def _handle_back_key(self) -> None:
        """Handle 'b' key press to return to browser.

        Follows SRP: Only handles back navigation logic.
        Follows DIP: Delegates navigation to app level.
        """
        if not self.browser_context:
            # Not launched from browser mode
            message_widget = self.query_one("#welcome-message", Static)
            message_widget.update("[yellow]⚠ Not launched from browser mode[/yellow]")
            self.set_timer(
                2.0,
                lambda: self._restore_loading_message() if not self.data_loaded else None
            )
            logger.debug("Back to browser unavailable - no browser context")
            return

        logger.info("User returning to browser from welcome screen")
        # Set flag on app and exit
        if hasattr(self.app, 'return_to_browser'):
            self.app.return_to_browser = True
        self.app.exit()

    def _handle_quit_key(self) -> None:
        """Handle 'q' key press to quit application.

        Follows SRP: Only handles quit logic.
        """
        logger.debug("User quit from welcome screen")
        self.app.exit()

    def _show_loading_warning(self) -> None:
        """Show warning when trying to continue before data loads.

        Follows SRP: Only handles warning display.
        Follows DRY: Reusable warning pattern.
        """
        message_widget = self.query_one("#welcome-message", Static)
        message_widget.update("[yellow]⚠ Please wait for data to finish loading...[/yellow]")
        # Reset message after 2 seconds
        self.set_timer(2.0, lambda: self._restore_loading_message() if not self.data_loaded else None)

    def _restore_loading_message(self) -> None:
        """Restore the loading message.

        Follows SRP: Only handles message restoration.
        """
        message_widget = self.query_one("#welcome-message", Static)
        message_widget.update(f"Loading execution {self.execution_id[:8]}...")

    def mark_data_loaded(self) -> None:
        """Mark data as loaded and show continue prompt."""
        self.data_loaded = True
        message_widget = self.query_one("#welcome-message", Static)
        spinner_widget = self.query_one("#loading-spinner", Static)

        # Show success message
        message_widget.update("[bold green]✓[/bold green] Data loaded successfully!")
        spinner_widget.update("")

        # After brief pause, show continue prompt
        self.set_timer(0.5, self._show_continue_prompt)

        logger.debug("Data loaded, showing continue prompt")

    def _build_prompt_text(self, pulse: bool = False) -> str:
        """Build the continue prompt text based on context.

        Follows DRY: Single source of truth for prompt text.
        Follows OCP: Easy to extend with more keys.

        Args:
            pulse: Whether to apply pulse effect to Enter key

        Returns:
            Formatted prompt string
        """
        # Build key options based on context
        enter_key = "[reverse green]Enter[/reverse green]" if pulse else "[green]Enter[/green]"

        if self.browser_context:
            # Has browser context - show back option
            return f"[bold]Press {enter_key} to continue, [blue]B[/blue] for browser, or [red]Q[/red] to quit[/bold]"
        else:
            # No browser context - standard prompt
            return f"[bold]Press {enter_key} to continue or [red]Q[/red] to quit[/bold]"

    def _show_continue_prompt(self) -> None:
        """Show the 'Press Enter to continue' prompt with animation.

        Follows SRP: Only shows the initial prompt.
        """
        message_widget = self.query_one("#welcome-message", Static)
        message_widget.update(self._build_prompt_text(pulse=False))

        # Start pulsing Enter prompt
        self.set_interval(0.5, self._pulse_enter_prompt)

    def _pulse_enter_prompt(self) -> None:
        """Pulse the Enter key in the prompt.

        Follows SRP: Only handles prompt animation.
        Follows DRY: Uses _build_prompt_text() for consistency.
        """
        if not self.data_loaded:
            return

        message_widget = self.query_one("#welcome-message", Static)
        # Alternate between highlighted and normal
        pulse = self.spinner_index % 2 == 0
        message_widget.update(self._build_prompt_text(pulse=pulse))
