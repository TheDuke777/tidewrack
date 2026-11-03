import flet as ft

from tidewrack.core.data.loader import ContentError
from tidewrack.services.content import load_bundled_content
from tidewrack.ui.screens.game import GameScreen


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
    page.add(GameScreen(content).control)


if __name__ == "__main__":
    ft.run(main)
