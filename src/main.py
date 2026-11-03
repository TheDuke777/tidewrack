import flet as ft

from tidewrack.ui.screens.game import GameScreen


def main(page: ft.Page):
    page.title = "Tidewrack"
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.add(GameScreen().control)


if __name__ == "__main__":
    ft.run(main)
