import flet as ft

from tidewrack.version import get_build_info, version_label


def main(page: ft.Page):
    page.title = "Tidewrack"
    page.theme_mode = ft.ThemeMode.SYSTEM

    page.add(
        ft.SafeArea(
            expand=True,
            content=ft.Container(
                alignment=ft.Alignment.CENTER,
                content=ft.Column(
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Image(
                            src="tidewrack.png",
                            width=200,
                            height=200,
                            fit=ft.BoxFit.CONTAIN,
                            border_radius=24,
                            semantics_label="Tidewrack logo",
                        ),
                        ft.Text("Tidewrack", size=40, weight=ft.FontWeight.BOLD),
                        ft.Text(version_label(get_build_info()), key="version"),
                    ],
                ),
            ),
        )
    )


if __name__ == "__main__":
    ft.run(main)
