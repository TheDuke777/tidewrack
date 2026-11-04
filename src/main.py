import flet as ft

from tidewrack.core.data.loader import ContentError
from tidewrack.services.content import load_bundled_content
from tidewrack.services.settings import SettingsStore, settings_path
from tidewrack.services.storage import FileSaveStore, saves_dir
from tidewrack.ui.app import App


def main(page: ft.Page):
    page.title = "Tidewrack"
    page.theme_mode = ft.ThemeMode.SYSTEM
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
    App(page, FileSaveStore(saves_dir()), SettingsStore(settings_path()), content).show_picker()


if __name__ == "__main__":
    ft.run(main)
