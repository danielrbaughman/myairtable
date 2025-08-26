from typer import Typer

app = Typer()


@app.command()
def main():
    print("Hello from myairtable!")


if __name__ == "__main__":
    app()
