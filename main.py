from typer import Typer

app = Typer()


@app.command()
def meta():
    print("Hello from myairtable!")

@app.command()
def csv():
    print("Hello from the CSV command!")

@app.command()
def python():
    print("Hello from the Python command!")


if __name__ == "__main__":
    app()
