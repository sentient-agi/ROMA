"""Filter modal for browser screen."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Select, Static

if TYPE_CHECKING:
    from roma_dspy.tui.core.client import ApiClient


class BrowserFilterModal(ModalScreen[dict[str, str | None] | None]):
    """Modal for filtering executions in browser mode.

    Follows SOLID principles:
    - SRP: Only handles filter UI and returns filter data
    - OCP: Extensible via API client injection
    - LSP: Proper ModalScreen subclass
    - ISP: Minimal interface (just returns filter dict)
    - DIP: Depends on ApiClient abstraction
    """

    # Known execution statuses (DRY - single source of truth)
    EXECUTION_STATUSES = [
        ("All", None),  # (display_name, filter_value)
        ("Completed", "completed"),
        ("Failed", "failed"),
        ("Running", "running"),
        ("Pending", "pending"),
        ("Cancelled", "cancelled"),
    ]

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    CSS = """
    BrowserFilterModal {
        align: center middle;
    }

    #filter-dialog {
        width: 70;
        height: auto;
        max-height: 90%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }

    #filter-title {
        text-align: center;
        margin-bottom: 1;
        color: $accent;
    }

    .filter-row {
        layout: horizontal;
        height: auto;
        margin: 1 0;
    }

    .filter-label {
        width: 20;
        padding-top: 1;
    }

    .filter-select {
        width: 1fr;
    }

    Select {
        width: 100%;
    }

    #button-row {
        layout: horizontal;
        height: auto;
        margin-top: 2;
        align: center middle;
    }

    Button {
        margin: 0 1;
    }

    #help-text {
        margin-top: 1;
        color: $text-muted;
        text-align: center;
    }

    #loading-text {
        margin-top: 1;
        color: $warning;
        text-align: center;
    }
    """

    def __init__(
        self,
        api_client: ApiClient,
        current_status: str | None = None,
        current_profile: str | None = None,
        current_experiment: str | None = None
    ) -> None:
        """Initialize filter modal.

        Args:
            api_client: API client for fetching available options
            current_status: Current status filter
            current_profile: Current profile filter
            current_experiment: Current experiment filter
        """
        super().__init__()
        self.api_client = api_client
        self.current_status = current_status
        self.current_profile = current_profile
        self.current_experiment = current_experiment

        # Populated dynamically from API
        self.available_profiles: list[tuple[str, str | None]] = [("All", None)]
        self.available_experiments: list[tuple[str, str | None]] = [("All", None)]

    def compose(self) -> ComposeResult:
        """Compose filter modal layout with dropdown selects."""
        with VerticalScroll(id="filter-dialog"):
            yield Static("[bold]Filter Executions[/bold]", id="filter-title")

            # Status dropdown (static options)
            with Horizontal(classes="filter-row"):
                yield Label("Status:", classes="filter-label")
                yield Select(
                    options=[(label, value) for label, value in self.EXECUTION_STATUSES],
                    id="status-select",
                    classes="filter-select",
                    allow_blank=False
                )

            # Profile dropdown (dynamic from API)
            with Horizontal(classes="filter-row"):
                yield Label("Profile:", classes="filter-label")
                yield Select(
                    options=self.available_profiles,
                    id="profile-select",
                    classes="filter-select",
                    allow_blank=False
                )

            # Experiment dropdown (dynamic from API)
            with Horizontal(classes="filter-row"):
                yield Label("Experiment:", classes="filter-label")
                yield Select(
                    options=self.available_experiments,
                    id="experiment-select",
                    classes="filter-select",
                    allow_blank=False
                )

            yield Static("", id="loading-text")

            with Horizontal(id="button-row"):
                yield Button("Apply", variant="primary", id="apply-button")
                yield Button("Clear", variant="default", id="clear-button")
                yield Button("Cancel", variant="default", id="cancel-button")

            yield Static(
                "[dim]Select 'All' to show all. Press Esc to cancel.[/dim]",
                id="help-text"
            )

    def on_mount(self) -> None:
        """Load dropdown options and set initial values."""
        # Set initial value for status (static options available immediately)
        if self.current_status is not None:
            try:
                self.query_one("#status-select", Select).value = self.current_status
            except Exception as e:
                logger.warning(f"Failed to set initial status: {e}")

        # Load dynamic options asynchronously
        self.run_worker(self._load_filter_options(), exclusive=True)

    def _extract_unique_values(self, executions: list[dict], field_name: str) -> set[str]:
        """Extract unique values for a field from executions.

        Follows SRP: Single responsibility for extraction logic.
        Follows DRY: Reusable for any field extraction.

        Args:
            executions: List of execution dicts
            field_name: Field to extract (e.g., "profile", "experiment_name")

        Returns:
            Set of unique non-empty values
        """
        values = set()
        for execution in executions:
            value = execution.get(field_name)
            if value:
                values.add(value)
        return values

    def _update_select_widget(
        self,
        select_id: str,
        options: list[tuple[str, str | None]],
        current_value: str | None,
        available_values: set[str]
    ) -> None:
        """Update a Select widget with options and set current value.

        Follows SRP: Single responsibility for widget updates.
        Follows DRY: Reusable for all Select widgets.

        Args:
            select_id: ID of Select widget to update
            options: List of (label, value) tuples
            current_value: Current filter value to restore
            available_values: Set of available values for validation
        """
        select_widget = self.query_one(f"#{select_id}", Select)
        select_widget.set_options(options)

        # Set value if it exists in options, otherwise default to None (All)
        if current_value and current_value in available_values:
            try:
                select_widget.value = current_value
            except Exception as e:
                logger.warning(f"Failed to set {select_id} value to {current_value}: {e}")
                select_widget.value = None
        else:
            select_widget.value = None

    async def _load_filter_options(self) -> None:
        """Fetch available profiles and experiments from API.

        Follows SRP: Orchestrates data fetching and widget updates.
        Follows DRY: Uses helper methods to avoid duplication.
        """
        try:
            self.query_one("#loading-text", Static).update("[yellow]Loading options...[/yellow]")

            # Fetch all executions to extract unique profiles and experiments
            response = await self.api_client.list_executions(limit=1000)
            executions = response.get("executions", [])

            # Extract unique values (DRY - reusable method)
            profiles = self._extract_unique_values(executions, "profile")
            experiments = self._extract_unique_values(executions, "experiment_name")

            # Format options (DRY - consistent pattern)
            self.available_profiles = [("All", None)] + sorted([(p, p) for p in profiles])
            self.available_experiments = [("All", None)] + sorted([(e, e) for e in experiments])

            # Update widgets (DRY - reusable method)
            self._update_select_widget(
                "profile-select",
                self.available_profiles,
                self.current_profile,
                profiles
            )
            self._update_select_widget(
                "experiment-select",
                self.available_experiments,
                self.current_experiment,
                experiments
            )

            self.query_one("#loading-text", Static).update("")
            logger.info(f"Loaded {len(profiles)} profiles, {len(experiments)} experiments")

        except Exception as e:
            logger.error(f"Failed to load filter options: {e}")
            self.query_one("#loading-text", Static).update(
                f"[red]Failed to load options: {str(e)[:50]}[/red]"
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events.

        Args:
            event: Button press event
        """
        if event.button.id == "apply-button":
            self._apply_filters()
        elif event.button.id == "clear-button":
            self._clear_filters()
        elif event.button.id == "cancel-button":
            self.action_cancel()

    def _apply_filters(self) -> None:
        """Apply filters and dismiss modal.

        Follows SRP: Only extracts values and returns data.
        """
        status_select = self.query_one("#status-select", Select)
        profile_select = self.query_one("#profile-select", Select)
        experiment_select = self.query_one("#experiment-select", Select)

        # Get values from Select widgets (Select.value is already the tuple value)
        status = status_select.value
        profile = profile_select.value
        experiment = experiment_select.value

        logger.info(f"Applying filters: status={status}, profile={profile}, experiment={experiment}")

        # Return filter dict
        self.dismiss({
            "status": status,
            "profile": profile,
            "experiment": experiment
        })

    def _clear_filters(self) -> None:
        """Clear all filters by setting to 'All' option.

        Follows DRY: Single method to reset all filters.
        """
        logger.info("Clearing all filters")

        # Set all selects to "All" (first option, value=None)
        self.query_one("#status-select", Select).value = None
        self.query_one("#profile-select", Select).value = None
        self.query_one("#experiment-select", Select).value = None

        # Return empty filters
        self.dismiss({
            "status": None,
            "profile": None,
            "experiment": None
        })

    def action_cancel(self) -> None:
        """Cancel and close modal without changes."""
        logger.debug("Filter modal cancelled")
        self.dismiss(None)
