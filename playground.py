from typer import Typer

app = Typer()


@app.command()
def main():
    """Playground"""
    pass


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    app()
