import sys
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.markdown import Markdown

from config.settings import settings
from modules.sheets.sync import sheet_sync
from modules.rag.knowledge_base import knowledge_base
from core.gemini_brain import gemini_brain, FALLBACK_MESSAGE

console = Console()

def run_cli():
    console.print(Panel.fit(
        f"[bold cyan]🎓 {settings.ADMIN_NAME}'s Autonomous AI CR Assistant Agent (Phase 1 CLI Playground)[/bold cyan]\n"
        f"[green]Representative:[/green] {settings.ADMIN_NAME} | [green]Batch:[/green] {settings.BATCH_NAME} (Sec {settings.SECTION_NAME})\n"
        f"[yellow]University:[/yellow] {settings.UNIVERSITY_NAME} ({settings.DEPARTMENT_NAME})\n\n"
        f"[dim]Commands: 'exit' to quit | '!admin' to toggle Admin mode | '!sync' to resync Sheet | '!routine <day>' to preview[/dim]",
        border_style="cyan"
    ))

    # Initial Sync
    with console.status("[bold green]Connecting to Master Google Sheet and local knowledge base..."):
        try:
            stats = sheet_sync.sync_all()
            knowledge_base.load_all()
            console.print(f"[bold green]✔ Synced successfully![/bold green] Routine Slots: {stats['routine_slots']} | Faculty: {stats['faculty_count']} | Docs: {len(knowledge_base.documents)}")
        except Exception as e:
            console.print(f"[bold yellow]⚠ Running with local cache / offline fallback: {e}[/bold yellow]")

    is_admin = False

    while True:
        try:
            role_prompt = f"[bold red]👑 {settings.ADMIN_NAME} (Admin)[/bold red]" if is_admin else "[bold blue]👤 Student[/bold blue]"
            user_input = Prompt.ask(f"\n{role_prompt} > ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "q"]:
                console.print(f"[dim]Goodbye {settings.ADMIN_NAME}! 🚀[/dim]")
                break

            if user_input.lower() == "!admin":
                is_admin = not is_admin
                state_str = "ENABLED" if is_admin else "DISABLED"
                console.print(f"[bold magenta]Admin mode {state_str}.[/bold magenta]")
                continue

            if user_input.lower().startswith("!routine"):
                parts = user_input.split()
                day = parts[1] if len(parts) > 1 else "Sunday"
                msg = sheet_sync.format_routine_message(day)
                console.print(Panel(msg, title=f"Broadcast Preview ({day.capitalize()})", border_style="green"))
                continue

            if user_input.lower().startswith("!messenger"):
                raw_text = user_input[len("!messenger"):].strip()
                if not raw_text:
                    console.print("[yellow]Usage: !messenger <incoming message text>[/yellow]")
                    continue
                from modules.bridge.messenger_filter import messenger_filter
                with console.status("[cyan]AI analyzing Messenger message..."):
                    res = messenger_filter.filter_and_process("CR Group Member", raw_text)
                if res.get("is_notice"):
                    console.print(Panel(
                        f"[bold green]✔ NOTICE DETECTED ({res.get('category')})[/bold green]\n\n"
                        f"{res.get('polished_notice')}\n\n"
                        f"[dim]Auto-relayed to WhatsApp Notice Group: {settings.MESSENGER_AUTO_RELAY}[/dim]",
                        title="📢 Cross-Platform Relay (Messenger -> WhatsApp)",
                        border_style="green"
                    ))
                else:
                    console.print(Panel(
                        f"[bold yellow]❌ IGNORED (Not an official notice)[/bold yellow]\n\n"
                        f"Reason: {res.get('reason', 'Casual conversation')}\n"
                        f"Raw text: {raw_text}",
                        title="Messenger Filter Result",
                        border_style="yellow"
                    ))
                continue

            # Process through Brain
            with console.status("[cyan]AI Assistant thinking..."):
                reply, is_fallback = gemini_brain.process_query(
                    sender_id="cli_admin" if is_admin else "cli_student",
                    sender_name=settings.ADMIN_NAME if is_admin else "Batch Student",
                    message=user_input,
                    is_admin=is_admin
                )

            # Display response
            if is_fallback:
                border_color = "yellow"
                title = "🤖 AI Assistant (Strict Fallback Triggered)"
            else:
                border_color = "cyan"
                title = "🤖 AI Assistant Response"

            console.print(Panel(reply, title=title, border_style=border_color))

        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session closed.[/dim]")
            break

if __name__ == "__main__":
    run_cli()
