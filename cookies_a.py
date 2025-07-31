import requests

session = requests.Session()
print(session.cookies.get_dict())  # {}

print('-' * 50)

response = session.get('http://google.com')

# {'AEC': 'Ad49MVGzf2rt5u6ObCPLjVzjrRqRMuYhCFG3iH7Ui8-banKZJ3dpZ_4wCA'}
print(session.cookies.get_dict())

print('-' * 50)

for c in session.cookies:
    print(f"{c.name} | {c.value} | {c.domain} | {c.path}")

print('-' * 50)

print(vars(c))
