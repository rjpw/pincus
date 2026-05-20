import asyncio
import httpx
import os
import ssl

from dotenv import load_dotenv

from pathlib import Path

from rich.json import JSON

from textual import on
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Footer, Header, Input, Label, Static

class PincusApp(App):
    """
    Main application.
    """

    base_url = None
    client_cert = None
    server_cert = None

    def __init__(self, 
                 driver_class = None, 
                 css_path = None, 
                 watch_css = False, 
                 ansi_color = None, 
                 incus_host = "localhost", 
                 incus_port = "8443"):
        
        super().__init__(driver_class, css_path, watch_css, ansi_color)
        home = Path.home()
        self.client_cert = (f"{home}/.config/incus/client.crt", f"{home}/.config/incus/client.key")
        self.server_cert = f"{home}/.config/incus/servercerts/{incus_host}.crt"
        self.base_url = f"https://{incus_host}:{incus_port}/1.0"


    BINDINGS = [("ctrl+q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Enter an endpoint (e.g. instances)")
        # yield Button("Submit query", variant="primary", id="submit_btn")
        yield VerticalScroll(Static(id="results"), id="results-container")
        yield Footer()

    @on(Input.Submitted)
    def handle_enter_key(self, event: Input.Submitted) -> None:
        self.update_output(event.value)

    @on(Button.Pressed, "#submit_btn")
    def handle_button_click(self) -> None:
        input_widget = self.query_one(Input)
        self.update_output(input_widget.value)

    def update_output(self, text: str) -> None:
        """A coroutine to handle a text changed message."""
        if text.strip():
            asyncio.create_task(self.call_incus(text.strip()))
        else:
            # Clear the results
            self.query_one("#results", Static).update()

    async def call_incus(self, endpoint: str) -> None:
        """Calls the Incus API"""
        url = f"{self.base_url}/{endpoint}"
        ssl_ctx = ssl.create_default_context(cafile=self.server_cert)
        ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        async with httpx.AsyncClient(cert=self.client_cert, verify=ssl_ctx) as client:
            results = (await client.get(url)).text
        
        if endpoint == self.query_one(Input).value:
            self.query_one("#results", Static).update(JSON(results))


if __name__ == "__main__":
    load_dotenv()
    incus_remote_host = os.getenv("INCUS_REMOTE_HOST")
    incus_remote_port = os.getenv("INCUS_REMOTE_PORT")
    PincusApp(css_path="pincus.tcss", incus_host=incus_remote_host, incus_port=incus_remote_port).run()
    
