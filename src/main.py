import flet as ft

from tidewrack.core.data.loader import ContentError
from tidewrack.services.content import load_bundled_content
from tidewrack.services.settings import SettingsStore, settings_path
from tidewrack.services.storage import FileSaveStore, saves_dir
from tidewrack.ui.app import App
from tidewrack.ui.theme import Theming


def main(page: ft.Page):
    page.title = "Tidewrack"
    page.theme_mode = ft.ThemeMode.SYSTEM
    settings = SettingsStore(settings_path())
    Theming(page, settings).start()
    try:
        content = load_bundled_content()
    except ContentError as e:
        # CI validates content, so this means a broken build; show why, not a blank app.
        page.add(
            ft.SafeArea(
                content=ft.Column(
                    scroll=ft.ScrollMode.AUTO,
                    controls=[
                        ft.Text("Tidewrack couldn't load its game data.", size=20),
                        *(ft.Text(problem, selectable=True) for problem in e.problems),
                    ],
                )
            )
        )
        return
    App(page, FileSaveStore(saves_dir()), settings, content).start()


if __name__ == "__main__":
    ft.run(main)
