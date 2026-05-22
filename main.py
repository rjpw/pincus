# import asyncio
import httpx
import json
import os
import ssl

from dotenv import load_dotenv

from pathlib import Path

from rich.json import JSON
from rich.text import Text as RichText

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import  Footer, DataTable, Static
from textual_terminal import Terminal

class IncusClient:

    def __init__(self):
        load_dotenv()
        home = Path.home()
        incus_remote_host = os.getenv("INCUS_REMOTE_HOST")
        incus_remote_port = os.getenv("INCUS_REMOTE_PORT")

        self.base_url = f"https://{incus_remote_host}:{incus_remote_port}/1.0"
        self.cert = (f"{home}/.config/incus/client.crt", f"{home}/.config/incus/client.key")
        self.ssl_ctx = ssl.create_default_context(
            cafile=f"{home}/.config/incus/servercerts/{incus_remote_host}.crt"
        )

    async def get_instances(self) -> list[dict]:
        async with httpx.AsyncClient(cert=self.cert, verify=self.ssl_ctx) as c:
            resp = await c.get(f"{self.base_url}/instances?recursion=1")
        return resp.json().get("metadata", [])

    async def set_state(self, name: str, action: str) -> str:
        body = {"action": action}
        async with httpx.AsyncClient(cert=self.cert, verify=self.ssl_ctx) as c:
            resp = await c.put(f"{self.base_url}/instances/{name}/state", json=body)
        return resp.json().get("status", "")

class IncusTerminal(Terminal):

    CSS_PATH = "pincus.tcss"
    
    instance_name = None

    class Disconnected(Message):
        pass

    def __init__(self, command: str, instance_name: str, **kwargs):
        super().__init__(command=command, **kwargs)
        self.instance_name = instance_name

    def stop(self) -> None:
        super().stop()
        self.post_message(self.Disconnected())

    def on_mount(self) -> None:
        self.border_title = self.instance_name
        self.border_subtitle = "type 'exit' to close"

    def _on_key(self, event) -> None:
        if self.emulator is None:
            return
        event.stop()
        event.prevent_default()
        char = self.ctrl_keys.get(event.key) or event.character
        if char:
            self.send_queue.put_nowait(["stdin", char])


class TerminalModal(ModalScreen):

    CSS_PATH = "pincus.tcss"

    def __init__(self, instance_name: str):
        super().__init__()
        self.instance_name = instance_name

    def compose(self) -> ComposeResult:
        with Vertical(id="terminal-container"):
            yield IncusTerminal(
                command=f"incus exec {self.instance_name} -- bash",
                instance_name=self.instance_name,
                id="shell",
            )

    def on_mount(self) -> None:
        terminal = self.query_one("#shell", IncusTerminal)
        terminal.start()
        terminal.focus()

    def action_close(self) -> None:
        self.dismiss()

    def on_incus_terminal_disconnected(self) -> None:
        self.dismiss()

    def on_unmount(self) -> None:
        try:
            self.query_one("#shell", IncusTerminal).stop()
        except Exception:
            pass


class PincusApp(App):
    """
    Main application.
    """

    client = None

    CSS_PATH = "pincus.tcss"

    def __init__(self):
        super().__init__()
        self.client = IncusClient()

    BINDINGS = [
        ("s", "start_instance", "Start"),
        ("x", "stop_instance", "Stop"),
        ("r", "restart_instance", "Restart"),
        ("ctrl-q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        with Horizontal(id="top-pane"):
            yield DataTable(id="instance-list")
            with VerticalScroll(id="instance-detail"):
                yield Static(id="instance-detail-content")
        yield Footer()

    def on_mount(self) -> None:
        self.client = IncusClient()
        table = self.query_one("#instance-list", DataTable)
        table.add_columns("Name", "State")
        table.cursor_type = "row"
        self.call_after_refresh(self.refresh_instances)
        self.set_interval(5, self.refresh_instances)

    async def refresh_instances(self) -> None:
        self.instances = await self.client.get_instances()
        table = self.query_one("#instance-list", DataTable)
        cursor_row = table.cursor_row
        table.clear()
        for inst in self.instances:
            name = inst["name"]
            state = inst["status"]
            style = "green" if state == "Running" else "red"
            table.add_row(
                RichText(name, style=style),
                RichText(state, style=style),
                key=name,
            )
        if cursor_row is not None and cursor_row < table.row_count:
            table.move_cursor(row=cursor_row)

    def _selected_instance(self) -> dict | None:
        table = self.query_one("#instance-list", DataTable)
        if table.cursor_row is None:
            return None
        row_key = table.get_row_at(table.cursor_row)
        name = str(row_key[0])
        return next((i for i in self.instances if i["name"] == name), None)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        inst = self._selected_instance()
        if not inst:
            return
        detail = self.query_one("#instance-detail-content", Static)
        detail.update(JSON(json.dumps(inst, indent=2)))

    async def _do_state_action(self, action: str) -> None:
        inst = self._selected_instance()
        if not inst:
            return
        name = inst["name"]
        if action.capitalize() == "Stop":
            self.notify(f"Stopping {name}...", timeout=3)
        else:
            self.notify(f"{action.capitalize()}ing {name}...", timeout=3)
        await self.client.set_state(name, action)
        self.set_timer(2, self.refresh_instances)

    async def action_start_instance(self) -> None:
        await self._do_state_action("start")

    async def action_stop_instance(self) -> None:
        await self._do_state_action("stop")

    async def action_restart_instance(self) -> None:
        await self._do_state_action("restart")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        inst = self._selected_instance()
        if not inst or inst["status"] != "Running":
            self.notify(
                f"Cannot open shell: {inst['name'] if inst else '?'} is not running",
                severity="error",
                timeout=3,
            )
            return
        self.push_screen(TerminalModal(inst["name"]))

if __name__ == "__main__":
    app = PincusApp()
    app.run()
    