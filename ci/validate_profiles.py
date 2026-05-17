import yaml, os

for f in os.listdir('profiles'):
    if f.endswith('.yaml'):
        with open('profiles/' + f) as fh:
            yaml.safe_load(fh)
        print('OK: profiles/' + f)
