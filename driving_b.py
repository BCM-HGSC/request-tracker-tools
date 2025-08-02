import marimo

__generated_with = "0.14.13"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    return


@app.cell
def _():
    from submit import (
        BASE_URL,
        RTSession,
        dump_response,
    )
    return BASE_URL, RTSession, dump_response


@app.cell
def _(RTSession):
    session = RTSession()
    session.check_authorized()
    return (session,)


@app.cell
def _(session):
    session.authenticate()
    session.check_authorized()
    return


@app.cell
def _():
    # session.logout()
    # session.check_authorized()
    # _new_session = RTSession()
    # _new_session.check_authorized()
    return


@app.cell
def _(BASE_URL):
    def ticket_url(id_string: str, *parts) -> str:
        return "/".join([f"{BASE_URL}ticket/{id_string}"] + list(parts))
    return (ticket_url,)


@app.cell
def _(dump_response, session, ticket_url):
    def try_url(id_string: str, *parts) -> None:
        dump_response(
            session.get(ticket_url(id_string, *parts))
        )
    return (try_url,)


@app.cell
def _(try_url):
    try_url("37479", "links")
    return


@app.cell
def _(try_url):
    try_url("37479", "attachments")
    return


@app.cell
def _(try_url):
    try_url("37479", "history")
    return


@app.cell
def _(try_url):
    try_url("37479", "history/id/1487179")
    return


@app.cell
def _(try_url):
    try_url("37479", "attachments/1481673")
    return


@app.cell
def _(session):
    session.print_cookies()
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
