from typer import Typer

from output import AND, ID, Airtable, CompaniesDateField, CompaniesNumberField, CompaniesTextField, CompaniesBooleanField

app = Typer()


@app.command()
def main():
    """Playground"""
    companies = Airtable().companies.get(fields=["Name"])
    print(len(companies))
    name = CompaniesTextField("Name")
    status = CompaniesNumberField("#Status")
    date = CompaniesDateField("SQL Date")
    is_active = CompaniesBooleanField("# Hours from Wolcott")
    formula = AND(
        name.equals("test"),
        name == "Active",
        name != "Inactive",
        status == 5,
        status != 10,
        date >= "2023-01-01",
        date <= "2023-12-31",
        date == "2023-06-15",
        date != "2023-07-01",
        ID() == "rec1234567890",
        is_active(),
    )
    print(formula)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    app()
