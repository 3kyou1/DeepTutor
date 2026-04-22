"""
CLI memory commands for the two-file public memory system (SUMMARY/PROFILE).
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from deeptutor.services.memory import get_memory_service
from deeptutor.services.personalization import get_profile_import_service

from .common import maybe_run

console = Console()


def _read_pasted_text() -> str:
    return typer.get_text_stream("stdin").read()


def register(app: typer.Typer) -> None:
    @app.command("show")
    def memory_show(
        file: str = typer.Argument(
            "all", help="File to show: summary, profile, or all.",
        ),
    ) -> None:
        """Display memory file content."""
        svc = get_memory_service()
        if file == "all":
            snap = svc.read_snapshot()
            for label, content in [
                ("SUMMARY", snap.summary),
                ("PROFILE", snap.profile),
            ]:
                if content:
                    console.print(Panel(Markdown(content), title=f"[bold]{label}.md[/]"))
                else:
                    console.print(f"[dim]{label}.md: (empty)[/]")
        elif file in ("summary", "profile"):
            content = svc.read_file(file)
            if content:
                console.print(Panel(Markdown(content), title=f"[bold]{file.upper()}.md[/]"))
            else:
                console.print(f"[dim]{file.upper()}.md: (empty)[/]")
        else:
            console.print(f"[red]Unknown file: {file}. Use summary, profile, or all.[/]")

    @app.command("clear")
    def memory_clear(
        file: str = typer.Argument(
            "all", help="File to clear: summary, profile, or all.",
        ),
        force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation."),
    ) -> None:
        """Clear memory file(s)."""
        svc = get_memory_service()
        if file not in ("summary", "profile", "all"):
            console.print(f"[red]Unknown file: {file}[/]")
            raise typer.Exit(1)

        if not force:
            target = "all memory files" if file == "all" else f"{file.upper()}.md"
            if not typer.confirm(f"Clear {target}?"):
                raise typer.Abort()

        if file == "all":
            svc.clear_memory()
            console.print("[green]Cleared all memory files.[/]")
        else:
            svc.clear_file(file)
            console.print(f"[green]Cleared {file.upper()}.md.[/]")

    @app.command("import")
    def memory_import(
        provider: str | None = typer.Option(
            None,
            "--provider",
            help="Provider for folder import: codex | claude_code | cursor.",
        ),
        path: str | None = typer.Option(None, "--path", help="Provider root folder path."),
        paste: bool = typer.Option(False, "--paste", help="Paste raw historical text via stdin."),
        mode: str = typer.Option("merge", "--mode", help="Import mode: create | merge | overwrite."),
        language: str = typer.Option("zh", "--language", help="Profile language."),
    ) -> None:
        """Import provider history folders or pasted text and refresh profile sections."""
        if paste:
            console.print("[dim]Paste history content, then press Ctrl-D to finish.[/]")
            text = _read_pasted_text()
            source_type = "pasted_text"
            folder_path = None
            selected_provider = None
        else:
            if not provider:
                console.print("[red]--provider is required unless --paste is used.[/]")
                raise typer.Exit(1)
            if not path:
                console.print("[red]--path is required for folder imports.[/]")
                raise typer.Exit(1)
            text = ""
            source_type = "folder"
            folder_path = path
            selected_provider = provider

        service = get_profile_import_service()
        preview = maybe_run(
            service.preview_import(
                source_type=source_type,
                provider=selected_provider,
                folder_path=folder_path,
                text=text,
                mode=mode,
                language=language,
            )
        )

        preview_data = preview if isinstance(preview, dict) else preview.to_dict()
        console.print(f"[bold]Detected turns:[/] {preview_data['detected_turns']}")
        console.print(f"[bold]Effective signals:[/] {preview_data['effective_signal_count']}")
        console.print(f"[bold]Scanned sessions:[/] {preview_data.get('scanned_session_count', 0)}")
        if preview_data.get("provider"):
            console.print(f"[bold]Provider:[/] {preview_data['provider']}")
        warnings = preview_data["warnings"]
        if warnings:
            console.print(f"[yellow]Warnings:[/] {', '.join(warnings)}")
        console.print(Panel(Markdown(preview_data["generated_copa_markdown"]), title="[bold]CoPA Preview[/]"))
        console.print(
            Panel(
                Markdown(preview_data["generated_summary_markdown"]),
                title="[bold]Profile Summary Preview[/]",
            )
        )

        if not preview_data["can_apply"]:
            console.print("[red]Import does not contain enough usable signals.[/]")
            raise typer.Exit(1)

        if not typer.confirm("Apply imported profile updates?"):
            raise typer.Abort()

        result = maybe_run(
            service.apply_import(
                source_type=source_type,
                provider=selected_provider,
                folder_path=folder_path,
                text=text,
                mode=mode,
                language=language,
            )
        )
        result_data = result if isinstance(result, dict) else result.to_dict()
        console.print(Panel(Markdown(result_data["profile"]), title="[bold]Updated PROFILE.md[/]"))
