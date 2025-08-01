import marimo

__generated_with = "0.14.13"
app = marimo.App(width="medium")


@app.cell
def _():
    import http.cookiejar as cookiejar
    from pprint import pprint as pp
    from re import IGNORECASE, match
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
        IGNORECASE,
        Session,
        cookiejar,
        fetch_auth_cookie,
        fetch_password,
        getuser,
        match,
        print_cookies,
    )


@app.function
def dump_response(response):
    print(response.url)
    print(response.status_code, response.reason)
    print()
    for k, v in response.headers.items():
        print(f"{k}: {v}")
    print()
    print(response.text)


@app.cell
def _(BASE_URL, IGNORECASE, Session, match):
    def check_authorized(session: Session) -> bool:
        response = session.get(BASE_URL)
        response.raise_for_status()
        # dump_response(response)
        m = match(r"rt/[.0-9]+\s+200\sok", response.text, IGNORECASE)
        return bool(m)
    return (check_authorized,)


@app.cell
def _(cookiejar):
    def load_cookies(session):
        cookie_file = 'cookies.txt'
        cj = cookiejar.MozillaCookieJar(cookie_file)
        # Try to load existing cookies (if file exists)
        try:
            cj.load(ignore_discard=True, ignore_expires=True)
        except FileNotFoundError:
            pass
        session.cookies = cj
    return (load_cookies,)


@app.cell
def _(fetch_auth_cookie, s):
    def fetch_and_save_auth_cookie(session, user, password):
        fetch_auth_cookie(session, user, password)
        s.cookies.save(ignore_discard=True, ignore_expires=True)
    return (fetch_and_save_auth_cookie,)


@app.cell
def _(Session, fetch_and_save_auth_cookie, fetch_password, getuser):
    def authenticate(session: Session):
        user = getuser()
        password = fetch_password(user)
        fetch_and_save_auth_cookie(session, user, password)
    return


@app.cell
def _(BASE_URL, Session, s):
    def logout(session: Session) -> None:
        response = session.get(f"{BASE_URL}/logout")
        dump_response(response)
        s.cookies.clear()
        s.cookies.save()
    return (logout,)


@app.cell
def _(logout, s):
    logout(s)
    return


@app.cell
def _():
    return


@app.cell
def _():
    return


@app.cell
def _(Session):
    s = Session()
    s.verify = "rt.hgsc.bcm.edu.pem"
    return (s,)


@app.cell
def _(BASE_URL, check_authorized, print_cookies, s):
    print_cookies(s)
    print()
    dump_response(s.get(BASE_URL))
    print(check_authorized(s))
    return


@app.cell
def _(check_authorized, s):
    check_authorized(s)
    return


@app.cell
def _(load_cookies, s):
    load_cookies(s)
    return


@app.cell
def _(BASE_URL, check_authorized, print_cookies, s):
    print_cookies(s)
    print()
    dump_response(s.get(BASE_URL))
    print(check_authorized(s))
    return


@app.cell
def _(check_authorized, s):
    check_authorized(s)
    return


@app.cell
def _(BASE_URL):
    id_string = "37479"
    url = f"{BASE_URL}ticket/{id_string}/show"
    return (url,)


@app.cell
def _(s, url):
    response = s.get(url)
    dump_response(response)
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
