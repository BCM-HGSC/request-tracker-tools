import marimo

__generated_with = "0.13.6"
app = marimo.App(width="medium")


@app.cell
def _():
    import http.cookiejar as cookiejar
    from requests import Session

    from submit import (
        BASE_URL,
        fetch_auth_cookie,
        fetch_password,
        getuser,
        post,
        print_response_summary,
        print_cookies,
    )
    return (
        BASE_URL,
        Session,
        fetch_auth_cookie,
        fetch_password,
        getuser,
        print_cookies,
    )


@app.cell
def _(fetch_password, getuser):
    user = getuser()
    password = fetch_password(user)
    return password, user


@app.cell
def _(Session):
    s = Session()
    s.verify = "rt.hgsc.bcm.edu.pem"
    return (s,)


@app.cell
def _(BASE_URL, fetch_auth_cookie, password, s, user):
    fetch_auth_cookie(s, BASE_URL, user, password)
    return


@app.cell
def _(print_cookies, s):
    print_cookies(s)
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
