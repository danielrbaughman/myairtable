
from typer import Typer

from output import Airtable

app = Typer()

@app.command()
def main():
    """Playground"""
    jobs = Airtable().jobs.get()
    print(len(jobs))


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    app()
