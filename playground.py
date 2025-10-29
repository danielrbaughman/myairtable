from typer import Typer

from output import AND
from output.dynamic.orm_models.deals import DealsORM

app = Typer()


@app.command()
def main():
    """Playground"""
    formula = AND(
        DealsORM.f.name == "Test Deal",
        DealsORM.f.active(),
        DealsORM.f.mql_date_from_company > "2023-01-01",
        DealsORM.field_size_upcharge_h_samplingcharge_h_bill.eq(10),
        DealsORM.field_size_upcharge_h_samplingcharge_h_bill.gt(5),
    )
    print(formula)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    app()
