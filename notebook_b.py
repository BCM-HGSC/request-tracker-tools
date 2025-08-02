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
    return (RTSession,)


@app.cell
def _(RTSession):
    session = RTSession()
    session.check_authorized()
    try_url = session.try_url
    return session, try_url


@app.cell
def _():
    # session.logout()
    # session.check_authorized()
    # _new_session = RTSession()
    # _new_session.check_authorized()
    return


@app.cell
def _(session):
    session.authenticate()
    session.check_authorized()
    return


@app.cell
def _():
    T1 = "37479"
    return (T1,)


@app.cell
def _(T1, try_url):
    try_url(T1, "links")
    return


@app.cell
def _(T1, try_url):
    try_url(T1, "attachments")
    return


@app.cell
def _(T1, try_url):
    try_url(T1, "history")
    return


@app.cell
def _(T1, try_url):
    try_url(T1, "history/id/1487179")
    return


@app.cell
def _(T1, try_url):
    try_url(T1, "attachments/1481673")
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
