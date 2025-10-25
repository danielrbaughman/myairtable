from typer import Typer

from output import Airtable

app = Typer()


@app.command()
def main():
    """Playground"""
    companies = Airtable().companies.get()
    print(len(companies))


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    app()
