"""Synthetic stand-in for the private tooling module used by the generator tests."""
DIRS = {
    "A": ("Тест А", "hub-a", ["demo-consent"]),
    "B": ("Тест Б", "hub-b", ["demo-policy"]),
}
TRIGGER = {
    "demo-consent": "тестовая обработка данных",
    "demo-policy": "любая обработка",
}


def main():
    raise SystemExit("main() must not run on import")


if __name__ == "__main__":
    main()
